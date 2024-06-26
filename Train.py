import os
import argparse

import torch
import torch.optim as optim
from torch import nn
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, datasets
from my_dataset import MyDataSet
from modelForSwinModify import swinT as create_model
from utils import read_split_data, train_one_epoch, evaluate
from pytorchtoolsWuzhe import EarlyStopping


def collate_fn(batch):
    images, labels = tuple(zip(*batch))
    images = torch.stack(images, dim=0)
    labels = torch.as_tensor(labels)
    return images, labels


def main(args, indexForIter):
    # seed
    torch.manual_seed(42)
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")

    if os.path.exists("../weights") is False:
        os.makedirs("../weights")

    # tb_writer = SummaryWriter('./logs/model+CA+924/200for224-new{}2/'.format(indexForIter + 1))
    tb_writer = SummaryWriter('./logs/modelCompare/{}zhe/swin_Change_CA'.format(indexForIter + 1))

    train_images_path, train_images_label, val_images_path, val_images_label = read_split_data(args.data_path)
    Mean = [0.78547709, 0.69860765, 0.73417401]
    Std = [0.11043156, 0.16935408, 0.12508291]
    img_size = 224
    data_transform = {
        "train": transforms.Compose([
            transforms.Resize(int(img_size * 1.243)),
            transforms.RandomCrop(img_size),
            transforms.ColorJitter(contrast=0.3),
            transforms.RandomHorizontalFlip(),
            transforms.RandomAdjustSharpness(1),
            transforms.ToTensor(),
            transforms.Normalize(Mean, Std)]),

        "val": transforms.Compose([
            transforms.Resize(int(img_size * 1.243)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(Mean, Std)])}

    train_dataset = MyDataSet(images_path=train_images_path,
                              images_class=train_images_label,
                              transform=data_transform["train"])

    data_train1 = datasets.ImageFolder(
        ''.format(indexForIter + 1),
        transform=data_transform["train"])
    data_train = data_train1
    print("Train Data" + data_train.root)
    val_dataset = datasets.ImageFolder(
        ''.format(indexForIter + 1),
        transform=data_transform["val"])
    print("Val Data" + val_dataset.root)

    batch_size = args.batch_size
    nw = min([os.cpu_count(), batch_size if batch_size > 1 else 0, 8])  # number of workers
    print('Using {} dataloader workers every process'.format(nw))
    train_loader = torch.utils.data.DataLoader(data_train,
                                               batch_size=batch_size,
                                               shuffle=True,
                                               pin_memory=True,
                                               num_workers=nw,
                                               collate_fn=train_dataset.collate_fn)

    val_loader = torch.utils.data.DataLoader(val_dataset,
                                             batch_size=batch_size,
                                             shuffle=True,
                                             pin_memory=True,
                                             num_workers=nw
                                             )

    model = create_model(num_classes=args.num_classes, drop_rate=0.15).to(device)
    # print(model)

    if args.weights != "":
        assert os.path.exists(args.weights), "weights file: '{}' not exist.".format(args.weights)
        weights_dict = torch.load(args.weights, map_location=device)["model"]
        for k in list(weights_dict.keys()):
            if "head" in k:
                del weights_dict[k]
        model.load_state_dict(weights_dict, strict=False)

    if args.freeze_layers:
        for name, para in model.named_parameters():
            if "head" not in name:
                para.requires_grad_(False)
            else:
                print("training {}".format(name))

    pg = [p for p in model.parameters() if p.requires_grad]
    optimizer = optim.AdamW(pg, lr=args.lr, weight_decay=5E-2)

    scheduler = CosineAnnealingLR(optimizer, args.epochs + 10)

    for epoch in range(args.epochs):

        train_loss, train_acc = train_one_epoch(model=model,
                                                optimizer=optimizer,
                                                data_loader=train_loader,
                                                device=device,
                                                epoch=epoch)

        # validate
        val_loss, val_acc = evaluate(model=model,
                                     data_loader=val_loader,
                                     device=device,
                                     epoch=epoch)
        # change model and set various lr
        desc = "RESwin"
        early_stopping(val_acc, model, epoch, indexForIter + 1, desc)
        if early_stopping.early_stop:
            print("Early Stopping")
            break
        tags = ["train_loss", "train_acc", "val_loss", "val_acc", "learning_rate"]
        tb_writer.add_scalar(tags[0], train_loss, epoch)
        tb_writer.add_scalar(tags[1], train_acc, epoch)
        tb_writer.add_scalar(tags[2], val_loss, epoch)
        tb_writer.add_scalar(tags[3], val_acc, epoch)
        tb_writer.add_scalar(tags[4], optimizer.param_groups[0]["lr"], epoch)
        scheduler.step()

    tb_writer.close()


if __name__ == '__main__':
    for indexForIter in range(5):
        indexForIter = indexForIter + 0
        parser = argparse.ArgumentParser()
        parser.add_argument('--num_classes', type=int, default=8)
        parser.add_argument('--epochs', type=int, default=140)
        parser.add_argument('--batch-size', type=int, default=32)
        parser.add_argument('--lr', type=float, default=0.00008)
        parser.add_argument('--data-path', type=str,
                            default="".format(indexForIter + 1))
        parser.add_argument('--weights', type=str, default='',
                            help='initial weights path')
        parser.add_argument('--freeze-layers', type=bool, default=False)
        parser.add_argument('--device', default='cuda:1', help='device id (i.e. 0 or 0,1 or cpu)')
        early_stopping = EarlyStopping(15, verbose=True)
        opt = parser.parse_args()
        main(opt, indexForIter)
