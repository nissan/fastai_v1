
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################
        # file to edit: dev_nb/002b_augment_training.ipynb

from nb_002 import *

import typing, os
from typing import Dict, Any, AnyStr, List, Sequence, TypeVar, Tuple, Optional, Union

def normalize(x, mean,std):   return (x-mean[...,None,None]) / std[...,None,None]
def denormalize(x, mean,std): return x*std[...,None,None] + mean[...,None,None]

def normalize_batch(b, mean, std, do_y=False):
    x,y = b
    x = normalize(x,mean,std)
    if do_y: y = normalize(y,mean,std)
    return x,y

def normalize_funcs(mean, std, do_y=False, device=None):
    if device is None: device=default_device
    return (partial(normalize_batch, mean=mean.to(device),std=std.to(device)),
            partial(denormalize,     mean=mean,           std=std))

def transform_datasets(train_ds, valid_ds, test_ds=None, tfms=None, **kwargs):
    res = [DatasetTfm(train_ds, tfms[0],  **kwargs),
           DatasetTfm(valid_ds, tfms[1],  **kwargs)]
    if test_ds is not None: res.append(DatasetTfm(test_ds, tfms[1],  **kwargs))
    return res

# CIFAR 10 stats looked up on google
cifar_stats = (tensor([0.491, 0.482, 0.447]), tensor([0.247, 0.243, 0.261]))
cifar_norm,cifar_denorm = normalize_funcs(*cifar_stats)

def num_cpus():
    try:                   return len(os.sched_getaffinity(0))
    except AttributeError: return os.cpu_count()

default_cpus = min(16, num_cpus())

@dataclass
class DeviceDataLoader():
    dl: DataLoader
    device: torch.device
    tfms: List[Callable]=None
    collate_fn: Callable=data_collate
    def __post_init__(self):
        self.dl.collate_fn=self.collate_fn
        self.tfms = listify(self.tfms)

    def __len__(self): return len(self.dl)
    def __getattr__(self,k): return getattr(self.dl, k)

    def add_tfm(self,tfm):    self.tfms.append(tfm)
    def remove_tfm(self,tfm): self.tfms.remove(tfm)

    def proc_batch(self,b):
        b = to_device(b, self.device)
        for f in listify(self.tfms): b = f(b)
        return b

    def __iter__(self):
        self.gen = map(self.proc_batch, self.dl)
        return iter(self.gen)

    @classmethod
    def create(cls, dataset, bs=1, shuffle=False, device=default_device, tfms=tfms,
               num_workers=default_cpus, collate_fn=data_collate, **kwargs):
        return cls(DataLoader(dataset, batch_size=bs, shuffle=shuffle, num_workers=num_workers, **kwargs),
                   device=device, tfms=tfms, collate_fn=collate_fn)

class DataBunch():
    def __init__(self, train_dl:DataLoader, valid_dl:DataLoader, test_dl:DataLoader=None,
                 device:torch.device=None, tfms=None, path='.'):
        self.device = default_device if device is None else device
        self.train_dl = DeviceDataLoader(train_dl, self.device, tfms=tfms)
        self.valid_dl = DeviceDataLoader(valid_dl, self.device, tfms=tfms)
        self.test_dl  = DeviceDataLoader(test_dl,  self.device, tfms=tfms) if test_dl else None
        self.path = Path(path)

    @classmethod
    def create(cls, train_ds, valid_ds, test_ds=None,
               path='.', bs=64, ds_tfms=None, num_workers=default_cpus,
               tfms=None, device=None, size=None, **kwargs):
        datasets = [train_ds,valid_ds]
        if test_ds is not None: datasets.append(test_ds)
        if ds_tfms: datasets = transform_datasets(*datasets, tfms=ds_tfms, size=size, **kwargs)
        dls = [DataLoader(*o, num_workers=num_workers) for o in
               zip(datasets, (bs,bs*2,bs*2), (True,False,False))]
        return cls(*dls, path=path, device=device, tfms=tfms)

    def __getattr__(self,k): return getattr(self.train_ds, k)
    def holdout(self, is_test=False): return self.test_dl if is_test else self.valid_dl

    @property
    def train_ds(self): return self.train_dl.dl.dataset
    @property
    def valid_ds(self): return self.valid_dl.dl.dataset

def data_from_imagefolder(path, train='train', valid='valid', test=None, **kwargs):
    path=Path(path)
    train_ds = FilesDataset.from_folder(path/train)
    datasets = [train_ds, FilesDataset.from_folder(path/valid, classes=train_ds.classes)]
    if test: datasets.append(FilesDataset.from_single_folder(
        path/test,classes=train_ds.classes))
    return DataBunch.create(*datasets, path=path, **kwargs)

def conv_layer(ni, nf, ks=3, stride=1):
    return nn.Sequential(
        nn.Conv2d(ni, nf, kernel_size=ks, bias=False, stride=stride, padding=ks//2),
        nn.BatchNorm2d(nf),
        nn.LeakyReLU(negative_slope=0.1, inplace=True))

class ResLayer(nn.Module):
    def __init__(self, ni):
        super().__init__()
        self.conv1=conv_layer(ni, ni//2, ks=1)
        self.conv2=conv_layer(ni//2, ni, ks=3)

    def forward(self, x): return x + self.conv2(self.conv1(x))

class Darknet(nn.Module):
    def make_group_layer(self, ch_in, num_blocks, stride=1):
        return [conv_layer(ch_in, ch_in*2,stride=stride)
               ] + [(ResLayer(ch_in*2)) for i in range(num_blocks)]

    def __init__(self, num_blocks, num_classes, nf=32):
        super().__init__()
        layers = [conv_layer(3, nf, ks=3, stride=1)]
        for i,nb in enumerate(num_blocks):
            layers += self.make_group_layer(nf, nb, stride=2-(i==1))
            nf *= 2
        layers += [nn.AdaptiveAvgPool2d(1), Flatten(), nn.Linear(nf, num_classes)]
        self.layers = nn.Sequential(*layers)

    def forward(self, x): return self.layers(x)