import os
import utils.function as uf
from utils.data import Sequence
from utils.modules import ModelConfig, SubConfig
from utils.settings import *
from importlib import import_module
from argparse import ArgumentParser
from utils.modules.logger import Logger


class LMConfig(ModelConfig):
    def __init__(self, args=None):
        # ! INITIALIZE ARGS
        super(LMConfig, self).__init__()

        # ! LM Settings
        self.model = 'Bert'
        self.lr = 0.00002
        self.eq_batch_size = 36
        self.weight_decay = 0.01
        self.label_smoothing_factor = 0.1
        self.dropout = 0.1
        self.warmup_epochs = 0.2
        self.att_dropout = 0.1
        self.cla_dropout = 0.1
        self.cla_bias = 'T'
        self.load_best_model_at_end = 'T'

        self.save_folder = ''
        self.ce_reduction = 'mean'

        self.feat_shrink = '100'
        self.feat_shrink = ''
        self.eval_patience = 100000
        self.md = None  # Tobe initialized in sub module

        # ! Experiments Settings
        self.seed = 0
        self.wandb_name = ''
        self.wandb_id = ''
        self.dataset = (d := DEFAULT_DATASET)
        self.epochs = 4
        self.verbose = 1
        self.device = None
        self.wandb_on = False
        self.birth_time = uf.get_cur_time(t_format='%m_%d-%H_%M_%S')
        self._wandb = None

    def init(self):
        """Initialize path, logger, experiment environment
        These environment variables should only be initialized in the actual training process. In other cases, where we only want the config parameters parser/res_file, the init function should not be called.
        """

        self._path_init()
        self.wandb_init()
        self.logger = Logger(self)
        self.log = self.logger.log
        self.wandb_log = self.logger.wandb_log
        self.log(self)
        self._exp_init()
        return self

    para_prefix = {'dataset': '',
                   'model': '', 'lr': 'lr', 'eq_batch_size': 'bsz',
                   'weight_decay': 'wd', 'dropout': 'do', 'att_dropout': 'atdo', 'cla_dropout': 'cla_do',
                   'cla_bias': 'cla_bias',
                   'epochs': 'e', 'warmup_epochs': 'we', 'eval_patience': 'ef', 'label_smoothing_factor': 'lsf',
                   'feat_shrink': '', 'PrtMode': 'mode'}

    def _intermediate_args_init(self):
        """
        Parse intermediate settings that shan't be saved or printed.
        """
        self.mode = 'pre_train'
        self.md = self.meta_data[self.model]
        self.hf_model = self.md.hf_model
        self.father_model = self.md.father_model
        self.hidden_dim = int(self.feat_shrink) if self.feat_shrink else self.md.hidden_dim
        self._lm = SubConfig(self, self.para_prefix)

        # * Init LM settings using pre-train folder
        self.lm = self.get_lm_info(self.save_dir, self.model)

    def get_lm_info(self, lm_folder, model):
        return SN(folder=lm_folder,
                  emb=f'{lm_folder}/{model}.emb',
                  pred=f'{lm_folder}/{model}.pred',
                  ckpt=f'{lm_folder}/{model}.ckpt',
                  result=f'{lm_folder}/{model}.result')

    def _exp_init(self):
        super()._exp_init()  # will initialize the data

    def _data_args_init(self):
        # Dataset
        self.lm_md = self.md
        self.data = Sequence(self)

    meta_data = None

    @property
    def parser(self):
        parser = ArgumentParser("Experimental settings")
        parser.add_argument("-g", '--gpus', default='0', type=str,
                            help='a list of active gpu ids, separated by ",", "cpu" for cpu-only mode.')
        parser.add_argument("-d", "--dataset", type=str, default=DEFAULT_DATASET)
        parser.add_argument("-t", "--train_percentage", default=DEFAULT_D_INFO['train_ratio'], type=int)
        parser.add_argument("-v", "--verbose", default=1, type=int,
                            help='Verbose level, higher level generates more log, -1 to shut down')
        parser.add_argument('--tqdm_on', action="store_true", help='show log by tqdm or not')
        parser.add_argument("-w", "--wandb_name", default='OFF', type=str, help='Wandb logger or not.')
        parser.add_argument("--epochs", default=3, type=int)
        parser.add_argument("--seed", default=0, type=int)
        parser.add_argument("-m", "--model", default='TinyBert',
                            help='name of the model, such as Bert, TinyBert, Deberta, Distilbert, Electra, RoBerta.')
        parser.add_argument("-lr", "--lr", default=0.002, type=float, help='LM model learning rate')  # 2e-05
        parser.add_argument("-bsz", "--eq_batch_size", default=36, type=int)  #
        parser.add_argument("-per_bsz", "--per_device_bsz", default=36, type=int)  #
        parser.add_argument("-per_eval", "--per_eval_bsz", default=360, type=int)  #
        parser.add_argument("-per_infer", "--inf_batch_size", default=400, type=int)  #
        parser.add_argument("-gra", "--grad_steps", default=1, type=int)  # 梯度累积 18 bsz;
        parser.add_argument("-wd", "--weight_decay", default=0.01)
        parser.add_argument("-do", "--dropout", default=0.1, type=float)
        parser.add_argument("-atdo", "--att_dropout", default=0.1, type=float)
        parser.add_argument("-cla", "--cla_dropout", default=0.1, type=float)
        parser.add_argument("-cla_bias", "--cla_bias", default='T', help='Classification model bias')
        parser.add_argument("-wmp", "--warmup_epochs", default=0.2, type=float)  # 0.5 1.0 0.75
        parser.add_argument("-ef", "--eval_patience", default=50000, type=int)
        parser.add_argument("-CLD", "--cl_dim", default=128, type=int, help='The dimension of the contrastive space')
        parser.add_argument("-lsf", "--label_smoothing_factor", default=0.1, type=float)
        parser.add_argument("-ce", "--ce_reduction", default='mean')
        # parser.add_argument("-feat_shrink", "--feat_shrink", default=None, type=str)
        parser.add_argument("-wid", "--wandb_id", default=None, type=str)
        parser.add_argument("--device", default=None, type=str)
        parser.add_argument("--wandb_on", default=False, type=bool)
        parser.add_argument("-prt", "--pretrain_path", default=None, type=str)  # 本地模型的路径
        parser.add_argument("-prtMode", "--PrtMode", default=None, type=str)
        parser.add_argument("-inf_dir", "--inference_dir", default=None, type=str)
        parser.add_argument("-cache", "--cache_dir", default=None, type=str)
        parser.add_argument("-cl", "--cl_dir", default=None, type=str)
        parser.add_argument("-fz", "--freeze", default=None,
                            help='freeze control whether to freeze the lm model, its number means how many layers do not freezed.',
                            type=int)
        # For GNN
        parser.add_argument("-gnn-name", "--gnn-name", default='SAGE', type=str, help='The name of the GNN')
        parser.add_argument("-n-hidden", "--n-hidden", default=256, type=int, help="number of hidden units")
        parser.add_argument("-n-layers", "--n-layers", default=1, type=int, help="number of layers")
        parser.add_argument("-n-heads", "--n-heads", type=int, default=3, help="number of heads")
        # For Sampler
        parser.add_argument("-sampler-way", "--sampler-way", type=str, default='default', help="the sampler way")
        # add fanouts
        parser.add_argument("--fanouts", default=1, type=int, help="fanouts")
        parser.add_argument("--metric", default='acc', type=str, help="the metric")
        # For split datasets
        parser.add_argument("--train_ratio", default=0.6, type=float)
        parser.add_argument("--val_ratio", default=0.2, type=float)
        parser.add_argument("--splits", default='random', type=str, help="The split datasets way")
        return parser

    @property
    def out_dir(self):
        if self.pretrain_path is not None:
            if self.PrtMode is not None:
                return f'{TEMP_PATH}{self.model}/ckpts/{self.PrtMode}/{self.dataset}/seed{self.seed}{self.model_cf_str}/'
            else:
                raise ValueError('Please input the PrtMode!')
        else:
            if self.PrtMode is not None:
                return f'{TEMP_PATH}{self.model}/{self.PrtMode}/{self.dataset}/seed{self.seed}{self.model_cf_str}/'
            else:
                return f'{TEMP_PATH}{self.model}/ckpts/{self.dataset}/seed{self.seed}{self.model_cf_str}/'

    @property
    def save_dir(self):
        if self.pretrain_path is not None:
            return f'{TEMP_PATH}{self.model}/PRT/{self.dataset}/seed{self.seed}{self.model_cf_str}'
        else:
            if self.PrtMode is not None:
                return f'{TEMP_PATH}{self.model}/PrtMode/{self.dataset}/seed{self.seed}{self.model_cf_str}'
            else:
                return f'{TEMP_PATH}{self.model}/finetune/{self.dataset}/seed{self.seed}{self.model_cf_str}'

    @property
    def model_cf_str(self):
        return self._lm.f_prefix


# ! LM Settings
LM_SETTINGS = {}
LM_MODEL_MAP = {
    'Deberta-large': 'Deberta',
    'TinyBert': 'Bert',
    'Roberta-large': 'RoBerta',
    'LinkBert-large': 'LinkBert',
    'Bert-large': 'Bert',
    'GPT2': 'GPT',
    'GPT2-large': 'GPT',
    'Electra-large': 'Electra',
    'Electra-base': 'Electra',
}


# ! Need
def get_lm_model():
    return LMConfig().parser.parse_known_args()[0].model


def get_lm_trainer(model, name=None):
    if name == 'TNP':
        from TNP_trainer import TNPTrainer as LMTrainer
    elif name == 'TRP':
        from Trainer.TRP_trainer import TRPTrainer as LMTrainer
    elif name == 'TCL':
        from Trainer.TCL_trainer import TCLTrainer as LMTrainer
    elif name == 'INF':
        from Trainer.Inf_trainer import LmInfTrainer as LMTrainer
    elif name == 'TDK':
        from Trainer.TDK_trainer import TDK_Trainer as LMTrainer
    elif name == 'CL_DK':
        from Trainer.TCL_DK_trainer import TCL_DK_Trainer as LMTrainer
    elif name == 'Tlink':
        from Trainer.TLink_trainer import TLink_Trainer as LMTrainer
    elif name == 'COT':
        from Trainer.Co_Trainer import CoT_Trainer as LMTrainer
    else:
        from lm_trainer import LMTrainer as LMTrainer
    return LMTrainer


def get_lm_config(model):
    model = LM_MODEL_MAP[model] if model in LM_MODEL_MAP else model
    return import_module(f'{model}').Config


