#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import math
import time
import wandb
import numpy as np
import torch as th
import torch.nn.functional as F
import torch.optim as optim
from matplotlib import pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from model.GNN_library import GIN, GCN
from model.GNN_arg import args_init
from model.Dataloader import load_data
from ogb.nodeproppred import DglNodePropPredDataset

device = None
in_feats, n_classes = None, None
epsilon = 1 - math.log(2)


def gen_model(args):
    if args.model_name == 'GIN':
        model = GIN(
            in_feats,
            args.n_hidden,
            n_classes,
            args.n_layers,
            args.num_mlp_layers,
            args.input_drop,
            args.learning_eps,
            args.neighbor_pooling_type,
            )
    elif args.model_name == 'GCN':
        model = GCN(
            in_feats,
            args.n_hidden,
            n_classes,
            args.n_layers,
            F.relu,
            args.dropout,
            args.input_drop,
        )
    else:
        raise ValueError('Not implement!')
    return model


def cross_entropy(x, labels):
    y = F.cross_entropy(x, labels[:, 0], reduction="mean", label_smoothing=0.1)
    y = th.log(epsilon + y) - math.log(epsilon)
    return th.mean(y)


def compute_acc(pred, labels):
    """
    Compute the accuracy of prediction given the labels.
    """
    return (th.argmax(pred, dim=1) == labels).float().sum() / len(pred)



def adjust_learning_rate(optimizer, lr, epoch):
    if epoch <= 50:
        for param_group in optimizer.param_groups:
            param_group["lr"] = lr * epoch / 50


def train(model, graph, feat, labels, train_idx, optimizer):
    model.train()

    optimizer.zero_grad()
    pred = model(graph, feat)
    loss = cross_entropy(pred[train_idx], labels[train_idx])
    loss.backward()
    optimizer.step()

    return loss, pred


@th.no_grad()
def evaluate(
    model, graph, feat, labels, train_idx, val_idx, test_idx
):
    model.eval()
    with th.no_grad():
        pred = model(graph, feat)
    val_loss = cross_entropy(pred[val_idx], labels[val_idx])
    test_loss = cross_entropy(pred[test_idx], labels[test_idx])

    return (
        compute_acc(pred[train_idx], labels[train_idx]),
        compute_acc(pred[val_idx], labels[val_idx]),
        compute_acc(pred[test_idx], labels[test_idx]),
        val_loss,
        test_loss,
    )


def run(
    args, graph, feat, labels, train_idx, val_idx, test_idx, n_running
):
    # define model and optimizer
    model = gen_model(args)
    model = model.to(device)
    TRAIN_NUMBERS = sum(
        [np.prod(p.size()) for p in model.parameters() if p.requires_grad]
    )
    print(f"Number of params: {TRAIN_NUMBERS}")
    optimizer = optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.wd
    )
    lr_scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=0.5,
        patience=100,
        verbose=True,
        min_lr=1e-3,
    )

    # training loop
    total_time = 0
    best_val_acc, final_test_acc, best_val_loss = 0, 0, float("inf")


    for epoch in range(1, args.n_epochs + 1):
        tic = time.time()

        adjust_learning_rate(optimizer, args.lr, epoch)

        loss, pred = train(
            model, graph, feat, labels, train_idx, optimizer
        )
        acc = compute_acc(pred[train_idx], labels[train_idx])

        (
            train_acc,
            val_acc,
            test_acc,
            val_loss,
            test_loss,
        ) = evaluate(
            model,
            graph,
            feat,
            labels,
            train_idx,
            val_idx,
            test_idx,
        )
        wandb.log({'Train_loss': loss, 'Val_loss': val_loss, 'Test_loss': test_loss})
        lr_scheduler.step(loss)

        toc = time.time()
        total_time += toc - tic

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_val_acc = val_acc
            final_test_acc = test_acc

        if epoch % args.log_every == 0:
            print(
                f"Run: {n_running}/{args.n_runs}, Epoch: {epoch}/{args.n_epochs}, Average epoch time: {total_time / epoch:.2f}\n"
                f"Loss: {loss.item():.4f}, Acc: {acc:.4f}\n"
                f"Train/Val/Test loss: {loss:.4f}/{val_loss:.4f}/{test_loss:.4f}\n"
                f"Train/Val/Test/Best val/Final test acc: {train_acc:.4f}/{val_acc:.4f}/{test_acc:.4f}/{best_val_acc:.4f}/{final_test_acc:.4f}"
            )


    print("*" * 50)
    print(f"Best val acc: {best_val_acc}, Final test acc: {final_test_acc}")
    print("*" * 50)

    return best_val_acc, final_test_acc


def count_parameters(args):
    model = gen_model(args)
    return sum(
        [np.prod(p.size()) for p in model.parameters() if p.requires_grad]
    )


def main():
    global device, in_feats, n_classes
    argparser = args_init()
    args = argparser.parse_args()
    wandb.config = args
    wandb.init(config=args, reinit=True)

    if args.cpu:
        device = th.device("cpu")
    else:
        device = th.device("cuda:%d" % args.gpu)

    # ! load data
    data = load_data(name=args.data_name)
    graph, labels, train_idx, val_idx, test_idx = data

    # add reverse edges
    srcs, dsts = graph.all_edges()
    graph.add_edges(dsts, srcs)

    # add self-loop
    print(f"Total edges before adding self-loop {graph.number_of_edges()}")
    graph = graph.remove_self_loop().add_self_loop()
    print(f"Total edges after adding self-loop {graph.number_of_edges()}")

    if args.use_PLM:
        feat = th.from_numpy(np.load(args.use_PLM).astype(np.float32)).to(device)
        in_feats = feat.shape[1]
    else:
        feat = graph.ndata["feat"].to(device)
        in_feats = graph.ndata["feat"].shape[1]
    n_classes = (labels.max() + 1).item()
    graph.create_formats_()

    train_idx = train_idx.to(device)
    val_idx = val_idx.to(device)
    test_idx = test_idx.to(device)
    labels = labels.to(device)
    graph = graph.to(device)

    # run
    val_accs = []
    test_accs = []

    for i in range(args.n_runs):
        val_acc, test_acc = run(
            args, graph, feat, labels, train_idx, val_idx, test_idx, i
        )
        wandb.log({'Val_Acc': val_acc, 'Test_Acc': test_acc})
        val_accs.append(val_acc)
        test_accs.append(test_acc)

    print(f"Runned {args.n_runs} times")
    print("Val Accs:", val_accs)
    print("Test Accs:", test_accs)
    print(f"Average val accuracy: {np.mean(val_accs)} ± {np.std(val_accs)}")
    print(f"Average test accuracy: {np.mean(test_accs)} ± {np.std(test_accs)}")
    print(f"Number of params: {count_parameters(args)}")
    wandb.log({'Mean_Val_Acc': np.mean(val_accs), 'Mean_Test_Acc': np.mean(test_accs)})


if __name__ == "__main__":
    main()