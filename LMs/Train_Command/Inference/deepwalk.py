import numpy as np
import os
import dgl
import torch as th
from ogb.nodeproppred import DglNodePropPredDataset
from gensim.models import Word2Vec
import networkx as nx
from karateclub import DeepWalk

# Load graphs
g = dgl.load_graphs('TAG-Benchmark/data/amazon/Sports/Fit/Sports-Fitness.pt')[0][0]
g = dgl.to_bidirected(g)
nx_G = g.to_networkx()

# Deepwalk in the graph and then get the node embeddings with high topology information
model = DeepWalk(walk_number=10, walk_length=80, dimensions=128, workers=4, window_size=5, epochs=1,learning_rate=0.05, min_count=1,seed=42)  # node embedding algorithm

model.fit(nx_G)  # fit it on the graph
embedding = model.get_embedding()  # extract embeddings

np.save('TAG-Benchmark/data/amazon/Sports/Fit/deepwalk_feat.npy', embedding)
print("finish")