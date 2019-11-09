# %%
NOTEBOOK = False

# %%
if NOTEBOOK:
    # %reload_ext autoreload
    # %autoreload 2
    # %matplotlib inline
    pass

    # %%
    #  Make sure to install torchvision before running this notebook

    # %%
import numpy as np
from skimage.transform import resize

SIZE = (3, 128, 128)


class PytorchDatasetWrapper():
    def __init__(self, dataset):
        super().__init__()
        self.dataset = dataset

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        sample = self.dataset[index]
        data = np.array(sample[0]).astype(np.float32).transpose(2, 0, 1)
        return {'data': resize(data, SIZE),
                'label': sample[1],
                'id': f'sample{index}'}


# %%
import pathlib

# PATH = '/home/micha/data/imagewoof-160'
PATH = '/home/micha/data/imagenette-160'

PATH = pathlib.Path(PATH)
train_path = PATH / 'train'
val_path = PATH / 'val'

# %%
import torch
from torchvision.datasets import ImageFolder
from pltools.data import Transformer, ToTensor

from batchgenerators.transforms import ZeroMeanUnitVarianceTransform

pre_transforms = [ZeroMeanUnitVarianceTransform()]
train_transforms = []
post_transforms = [ToTensor(
    keys=('data', 'label'),
    dtypes=(('data', torch.float32), ('label', torch.int64)))]

train_dset = PytorchDatasetWrapper(ImageFolder(train_path))
train_transformer = Transformer(
    train_dset, pre_transforms + train_transforms + post_transforms)

val_dset = PytorchDatasetWrapper(ImageFolder(val_path))
val_transformer = Transformer(
    train_dset, pre_transforms + post_transforms)

# %%
import matplotlib.pyplot as plt
sample = train_dset[6]['data']
sample -= sample.min()
sample = sample / sample.max()
plt.imshow(sample.transpose(1, 2, 0))

# %%


# %%
import torch
from torch.nn import functional as F
from torchvision.models import resnet18
from pltools.train.module import PLTModule
from collections import defaultdict


class Classifier(PLTModule):
    def __init__(
        self,
        config,
        model=resnet18(
            pretrained=False,
            num_classes=10)):
        super().__init__(config, model=model)

    def training_step(self, batch, batch_nb):
        # REQUIRED
        x = batch["data"]
        y = batch["label"]
        y_hat = self.forward(x)

        loss = F.cross_entropy(y_hat, y)

        tensorboard_logs = {'train_loss': loss}

        return {'loss': loss,
                'log': tensorboard_logs}

    def validation_step(self, batch, batch_nb):
        # OPTIONAL
        x = batch["data"]
        y = batch["label"]
        y_hat = self.forward(x)

        val_loss = F.cross_entropy(y_hat, y, reduction='mean')

        # calculate acc
        with torch.no_grad():
            labels_hat = torch.argmax(y_hat.detach(), dim=1)
            val_acc = torch.sum(y == labels_hat) / (len(y) * 1.0)

            if batch_nb == 0:
                normed_batch = x.detach()
                normed_batch -= normed_batch.min()
                normed_batch = normed_batch / normed_batch.max()
                self.logger.experiment.add_images('first_val_batch', normed_batch)

        return {'val_loss': val_loss, 'val_acc': val_acc}

    def validation_end(self, outputs):
        # OPTIONAL
        avg_val = defaultdict(list)
        for listitem in outputs:
            for key, item in listitem.items():
                avg_val[key].append(item)

        avg_val = {key: torch.stack(item).mean()
                   for key, item in avg_val.items()}

        return {'avg_val_loss': avg_val['val_loss'], 'log': avg_val}

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.0003)


# %%
class Config:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataloader = {'batch_size': 32, 'num_workers': 4}
        self.train_dataloader = {**self.dataloader, "shuffle": True}


# %%
module = Classifier(Config())
module.train_transformer = train_transformer
module.val_transformer = val_transformer

# %%
if NOTEBOOK:
    from pltools.train import lr_find, plot_lr_curve
    lrs, losses = lr_find(module, gpu_id=0)
    plot_lr_curve(lrs, losses)


# %%
from pytorch_lightning import Trainer

trainer = Trainer(gpus=1, amp_level='O1', use_amp=False,
                  fast_dev_run=False, overfit_pct=0, max_nb_epochs=5,
                  min_nb_epochs=5)
trainer.fit(module)

# %%
