# Copyright (c) OpenMMLab. All rights reserved.
# Modified from https://github.com/open-mmlab/mmdetection
import torch
import torch.nn as nn
import torch.nn.functional as F
from mmcv.ops import sigmoid_focal_loss as _sigmoid_focal_loss

from mmseg.registry import MODELS
from .utils import weight_reduce_loss
iteartion=0
# This method is used when cuda is not available
def py_sigmoid_focal_loss(pred,
                          target,
                          one_hot_target=None,
                          weight=None,
                          gamma=2.0,
                          alpha=0.5,
                          class_weight=None,
                          valid_mask=None,
                          reduction='mean',
                          avg_factor=None):
    """PyTorch version of `Focal Loss <https://arxiv.org/abs/1708.02002>`_.

    Args:
        pred (torch.Tensor): The prediction with shape (N, C), C is the
            number of classes
        target (torch.Tensor): The learning label of the prediction with
            shape (N, C)
        one_hot_target (None): Placeholder. It should be None.
        weight (torch.Tensor, optional): Sample-wise loss weight.
        gamma (float, optional): The gamma for calculating the modulating
            factor. Defaults to 2.0.
        alpha (float | list[float], optional): A balanced form for Focal Loss.
            Defaults to 0.5.
        class_weight (list[float], optional): Weight of each class.
            Defaults to None.
        valid_mask (torch.Tensor, optional): A mask uses 1 to mark the valid
            samples and uses 0 to mark the ignored samples. Default: None.
        reduction (str, optional): The method used to reduce the loss into
            a scalar. Defaults to 'mean'.
        avg_factor (int, optional): Average factor that is used to average
            the loss. Defaults to None.
    """
    if isinstance(alpha, list):
        alpha = pred.new_tensor(alpha)
    pred_sigmoid = pred.sigmoid()
    target = target.type_as(pred)
    one_minus_pt = (1 - pred_sigmoid) * target + pred_sigmoid * (1 - target)
    focal_weight = (alpha * target + (1 - alpha) *
                    (1 - target)) * one_minus_pt.pow(gamma)

    loss = F.binary_cross_entropy_with_logits(
        pred, target, reduction='none') * focal_weight
    final_weight = torch.ones(1, pred.size(1)).type_as(loss)
    if weight is not None:
        if weight.shape != loss.shape and weight.size(0) == loss.size(0):
            # For most cases, weight is of shape (N, ),
            # which means it does not have the second axis num_class
            weight = weight.view(-1, 1)
        assert weight.dim() == loss.dim()
        final_weight = final_weight * weight
    if class_weight is not None:
        final_weight = final_weight * pred.new_tensor(class_weight)
    if valid_mask is not None:
        final_weight = final_weight * valid_mask
    loss = weight_reduce_loss(loss, final_weight, reduction, avg_factor)
    return loss


def sigmoid_focal_loss(pred,
                       target,
                       one_hot_target,
                       weight=None,
                       keep_loss_num_ratio=0.7,
                       gamma=2.0,
                       alpha=0.5,
                       class_weight=None,
                       valid_mask=None,
                       reduction='mean',
                       avg_factor=None):
    r"""A wrapper of cuda version `Focal Loss
    <https://arxiv.org/abs/1708.02002>`_.
    Args:
        pred (torch.Tensor): The prediction with shape (N, C), C is the number
            of classes.
        target (torch.Tensor): The learning label of the prediction. It's shape
            should be (N, )
        one_hot_target (torch.Tensor): The learning label with shape (N, C)
        weight (torch.Tensor, optional): Sample-wise loss weight.
        gamma (float, optional): The gamma for calculating the modulating
            factor. Defaults to 2.0.
        alpha (float | list[float], optional): A balanced form for Focal Loss.
            Defaults to 0.5.
        class_weight (list[float], optional): Weight of each class.
            Defaults to None.
        valid_mask (torch.Tensor, optional): A mask uses 1 to mark the valid
            samples and uses 0 to mark the ignored samples. Default: None.
        reduction (str, optional): The method used to reduce the loss into
            a scalar. Defaults to 'mean'. Options are "none", "mean" and "sum".
        avg_factor (int, optional): Average factor that is used to average
            the loss. Defaults to None.
    """
    # Function.apply does not accept keyword arguments, so the decorator
    # "weighted_loss" is not applicable
    txt_path = "/root/autodl-pub/CZX/mmsegmentation_czx/loss_focal_ohem_2_foreground_1_2_oneloss_change_pipeline.txt"
    global iteartion
    final_weight = torch.ones(1, pred.size(1)).type_as(pred)
    iteartion += 1 
    if isinstance(alpha, list):
        # _sigmoid_focal_loss doesn't accept alpha of list type. Therefore, if
        # a list is given, we set the input alpha as 0.5. This means setting
        # equal weight for foreground class and background class. By
        # multiplying the loss by 2, the effect of setting alpha as 0.5 is
        # undone. The alpha of type list is used to regulate the loss in the
        # post-processing process.
        loss = _sigmoid_focal_loss(pred.contiguous(), target.contiguous(),
                                   gamma, 0.5, None, 'none') * 2
        alpha = pred.new_tensor(alpha)
        final_weight = final_weight * (
            alpha * one_hot_target + (1 - alpha) * (1 - one_hot_target))
    else:
        loss = _sigmoid_focal_loss(pred.contiguous(), target.contiguous(),
                                   gamma, alpha, None, 'none')
    if weight is not None:
        if weight.shape != loss.shape and weight.size(0) == loss.size(0):
            # For most cases, weight is of shape (N, ),
            # which means it does not have the second axis num_class
            weight = weight.view(-1, 1)
        assert weight.dim() == loss.dim()
        final_weight = final_weight * weight
    if class_weight is not None:
        final_weight = final_weight * pred.new_tensor(class_weight)
    if valid_mask is not None:
        final_weight = final_weight * valid_mask
    if iteartion <= 40000:
        loss_write = loss * final_weight # 忽略的类别自然设置的weight=0
        loss_write = loss_write.mean(dim=1).contiguous()
        if iteartion%100 == 0 and str(pred.device)=='cuda:0':
            class_0_loss = loss_write[target==0].sum()
            class_1_loss = loss_write[target==1].sum()
            class_2_loss = loss_write[target==2].sum()
            class_3_loss = loss_write[target==3].sum()
            loss_each_class = [class_0_loss, class_1_loss, class_2_loss, class_3_loss]
            total_loss = class_0_loss+class_1_loss+class_2_loss+class_3_loss
            account_loss = [item / total_loss for item in loss_each_class]
            with open(txt_path, 'a+') as f:
                f.write('0:{:.3f}    1:{:.3f}    2:{:.3f}    3:{:.3f}\n'.format(account_loss[0], account_loss[1], account_loss[2], account_loss[3]))
        loss = weight_reduce_loss(loss, final_weight, reduction, avg_factor)
    elif 40000<iteartion<=54000:
        loss = loss * final_weight # 忽略的类别自然设置的weight=0
        loss = loss.mean(dim=1).contiguous()
        loss, index = loss.sort(descending=True)
        loss = loss[loss>0].contiguous()  # 只要loss>0的部分，相当于没有算那些0的loss，忽略可ingore_label
        num_loss_backward = int(loss.shape[0]*0.8)
        loss = loss[0:num_loss_backward].contiguous()
        index = index[0:num_loss_backward]
        target_loss = target[index]
        if iteartion%100 == 0 and str(pred.device)=='cuda:0':
            class_0_loss = loss[target_loss==0].sum()
            class_1_loss = loss[target_loss==1].sum()
            class_2_loss = loss[target_loss==2].sum()
            class_3_loss = loss[target_loss==3].sum()
            loss_each_class = [class_0_loss, class_1_loss, class_2_loss, class_3_loss]
            total_loss = class_0_loss+class_1_loss+class_2_loss+class_3_loss
            account_loss = [item / total_loss for item in loss_each_class]
            with open(txt_path, 'a+') as f:
                f.write('0:{:.3f}    1:{:.3f}    2:{:.3f}    3:{:.3f}\n'.format(account_loss[0], account_loss[1], account_loss[2], account_loss[3]))
        loss = loss.mean()
        
    elif 54000<iteartion<=70000:
        loss = loss * final_weight # 忽略的类别自然设置的weight=0
        loss = loss.mean(dim=1).contiguous()
        loss, index = loss.sort(descending=True)
        loss = loss[loss>0].contiguous()  # 只要loss>0的部分，相当于没有算那些0的loss，忽略可ingore_label
        num_loss_backward = int(loss.shape[0]*0.7)
        loss = loss[0:num_loss_backward].contiguous()
        index = index[0:num_loss_backward]
        target_loss = target[index]
        if iteartion%100 == 0 and str(pred.device)=='cuda:0':
            class_0_loss = loss[target_loss==0].sum()
            class_1_loss = loss[target_loss==1].sum()
            class_2_loss = loss[target_loss==2].sum()
            class_3_loss = loss[target_loss==3].sum()
            loss_each_class = [class_0_loss, class_1_loss, class_2_loss, class_3_loss]
            total_loss = class_0_loss+class_1_loss+class_2_loss+class_3_loss
            account_loss = [item / total_loss for item in loss_each_class]
            with open(txt_path, 'a+') as f:
                f.write('0:{:.3f}    1:{:.3f}    2:{:.3f}    3:{:.3f}\n'.format(account_loss[0], account_loss[1], account_loss[2], account_loss[3]))
        loss = loss.mean()
    elif 70000<iteartion<=77000:
        loss = loss * final_weight # 忽略的类别自然设置的weight=0
        loss = loss.mean(dim=1).contiguous()
        loss, index = loss.sort(descending=True)
        loss = loss[loss>0].contiguous()  # 只要loss>0的部分，相当于没有算那些0的loss，忽略可ingore_label
        num_loss_backward = int(loss.shape[0]*0.6)
        loss = loss[0:num_loss_backward].contiguous()
        index = index[0:num_loss_backward]
        target_loss = target[index]
        if iteartion%100 == 0 and str(pred.device)=='cuda:0':
            class_0_loss = loss[target_loss==0].sum()
            class_1_loss = loss[target_loss==1].sum()
            class_2_loss = loss[target_loss==2].sum()
            class_3_loss = loss[target_loss==3].sum()
            loss_each_class = [class_0_loss, class_1_loss, class_2_loss, class_3_loss]
            total_loss = class_0_loss+class_1_loss+class_2_loss+class_3_loss
            account_loss = [item / total_loss for item in loss_each_class]
            with open(txt_path, 'a+') as f:
                f.write('0:{:.3f}    1:{:.3f}    2:{:.3f}    3:{:.3f}\n'.format(account_loss[0], account_loss[1], account_loss[2], account_loss[3]))
        loss = loss.mean()
    elif 77000<iteartion<=80000:
        loss = loss * final_weight # 忽略的类别自然设置的weight=0
        loss = loss.mean(dim=1).contiguous()
        loss, index = loss.sort(descending=True)
        loss = loss[loss>0].contiguous()  # 只要loss>0的部分，相当于没有算那些0的loss，忽略可ingore_label
        num_loss_backward = int(loss.shape[0]*0.5)
        loss = loss[0:num_loss_backward].contiguous()
        index = index[0:num_loss_backward]
        target_loss = target[index]
        if iteartion%100 == 0 and str(pred.device)=='cuda:0':
            class_0_loss = loss[target_loss==0].sum()
            class_1_loss = loss[target_loss==1].sum()
            class_2_loss = loss[target_loss==2].sum()
            class_3_loss = loss[target_loss==3].sum()
            loss_each_class = [class_0_loss, class_1_loss, class_2_loss, class_3_loss]
            total_loss = class_0_loss+class_1_loss+class_2_loss+class_3_loss
            account_loss = [item / total_loss for item in loss_each_class]
            with open(txt_path, 'a+') as f:
                f.write('0:{:.3f}    1:{:.3f}    2:{:.3f}    3:{:.3f}\n'.format(account_loss[0], account_loss[1], account_loss[2], account_loss[3]))
        loss = loss.mean()
        

    return loss


@MODELS.register_module()
class FocalLoss_ohem(nn.Module):

    def __init__(self,
                 use_sigmoid=True,
                 gamma=2.0,
                 alpha=0.5,
                 reduction='mean',
                 keep_loss_num_ratio=0.7,
                 class_weight=None,
                 loss_weight=1.0,
                 loss_name='loss_focal_ohem'):
        """`Focal Loss <https://arxiv.org/abs/1708.02002>`_
        Args:
            use_sigmoid (bool, optional): Whether to the prediction is
                used for sigmoid or softmax. Defaults to True.
            gamma (float, optional): The gamma for calculating the modulating
                factor. Defaults to 2.0.
            alpha (float | list[float], optional): A balanced form for Focal
                Loss. Defaults to 0.5. When a list is provided, the length
                of the list should be equal to the number of classes.
                Please be careful that this parameter is not the
                class-wise weight but the weight of a binary classification
                problem. This binary classification problem regards the
                pixels which belong to one class as the foreground
                and the other pixels as the background, each element in
                the list is the weight of the corresponding foreground class.
                The value of alpha or each element of alpha should be a float
                in the interval [0, 1]. If you want to specify the class-wise
                weight, please use `class_weight` parameter.
            reduction (str, optional): The method used to reduce the loss into
                a scalar. Defaults to 'mean'. Options are "none", "mean" and
                "sum".
            class_weight (list[float], optional): Weight of each class.
                Defaults to None.
            loss_weight (float, optional): Weight of loss. Defaults to 1.0.
            loss_name (str, optional): Name of the loss item. If you want this
                loss item to be included into the backward graph, `loss_` must
                be the prefix of the name. Defaults to 'loss_focal'.
        """
        super().__init__()
        assert use_sigmoid is True, \
            'AssertionError: Only sigmoid focal loss supported now.'
        assert reduction in ('none', 'mean', 'sum'), \
            "AssertionError: reduction should be 'none', 'mean' or " \
            "'sum'"
        assert isinstance(alpha, (float, list)), \
            'AssertionError: alpha should be of type float'
        assert isinstance(gamma, float), \
            'AssertionError: gamma should be of type float'
        assert isinstance(loss_weight, float), \
            'AssertionError: loss_weight should be of type float'
        assert isinstance(loss_name, str), \
            'AssertionError: loss_name should be of type str'
        assert isinstance(class_weight, list) or class_weight is None, \
            'AssertionError: class_weight must be None or of type list'
        self.use_sigmoid = use_sigmoid
        self.gamma = gamma
        self.alpha = alpha
        self.reduction = reduction
        self.class_weight = class_weight
        self.loss_weight = loss_weight
        self._loss_name = loss_name
        self.keep_loss_num_ratio = keep_loss_num_ratio

    def forward(self,
                pred,
                target,
                weight=None,
                avg_factor=None,
                reduction_override=None,
                ignore_index=255,
                **kwargs):
        """Forward function.

        Args:
            pred (torch.Tensor): The prediction with shape
                (N, C) where C = number of classes, or
                (N, C, d_1, d_2, ..., d_K) with K≥1 in the
                case of K-dimensional loss.
            target (torch.Tensor): The ground truth. If containing class
                indices, shape (N) where each value is 0≤targets[i]≤C−1,
                or (N, d_1, d_2, ..., d_K) with K≥1 in the case of
                K-dimensional loss. If containing class probabilities,
                same shape as the input.
            weight (torch.Tensor, optional): The weight of loss for each
                prediction. Defaults to None.
            avg_factor (int, optional): Average factor that is used to
                average the loss. Defaults to None.
            reduction_override (str, optional): The reduction method used
                to override the original reduction method of the loss.
                Options are "none", "mean" and "sum".
            ignore_index (int, optional): The label index to be ignored.
                Default: 255
        Returns:
            torch.Tensor: The calculated loss
        """
        assert isinstance(ignore_index, int), \
            'ignore_index must be of type int'
        assert reduction_override in (None, 'none', 'mean', 'sum'), \
            "AssertionError: reduction should be 'none', 'mean' or " \
            "'sum'"
        assert pred.shape == target.shape or \
               (pred.size(0) == target.size(0) and
                pred.shape[2:] == target.shape[1:]), \
               "The shape of pred doesn't match the shape of target"

        original_shape = pred.shape

        # [B, C, d_1, d_2, ..., d_k] -> [C, B, d_1, d_2, ..., d_k]
        pred = pred.transpose(0, 1)
        # [C, B, d_1, d_2, ..., d_k] -> [C, N]
        pred = pred.reshape(pred.size(0), -1)
        # [C, N] -> [N, C]
        pred = pred.transpose(0, 1).contiguous()

        if original_shape == target.shape:
            # target with shape [B, C, d_1, d_2, ...]
            # transform it's shape into [N, C]
            # [B, C, d_1, d_2, ...] -> [C, B, d_1, d_2, ..., d_k]
            target = target.transpose(0, 1)
            # [C, B, d_1, d_2, ..., d_k] -> [C, N]
            target = target.reshape(target.size(0), -1)
            # [C, N] -> [N, C]
            target = target.transpose(0, 1).contiguous()
        else:
            # target with shape [B, d_1, d_2, ...]
            # transform it's shape into [N, ]
            target = target.view(-1).contiguous()
            valid_mask = (target != ignore_index).view(-1, 1)
            # avoid raising error when using F.one_hot()
            target = torch.where(target == ignore_index, target.new_tensor(0),
                                 target)

        reduction = (
            reduction_override if reduction_override else self.reduction)
        if self.use_sigmoid:
            num_classes = pred.size(1)
            if torch.cuda.is_available() and pred.is_cuda:
                if target.dim() == 1:
                    one_hot_target = F.one_hot(
                        target, num_classes=num_classes + 1)
                    if num_classes == 1:
                        one_hot_target = one_hot_target[:, 1]
                        target = 1 - target
                    else:
                        one_hot_target = one_hot_target[:, :num_classes]
                else:
                    one_hot_target = target
                    target = target.argmax(dim=1)
                    valid_mask = (target != ignore_index).view(-1, 1)
                calculate_loss_func = sigmoid_focal_loss
            else:
                one_hot_target = None
                if target.dim() == 1:
                    target = F.one_hot(target, num_classes=num_classes + 1)
                    if num_classes == 1:
                        target = target[:, 1]
                    else:
                        target = target[:, num_classes]
                else:
                    valid_mask = (target.argmax(dim=1) != ignore_index).view(
                        -1, 1)
                calculate_loss_func = py_sigmoid_focal_loss

            loss_cls = self.loss_weight * calculate_loss_func(
                pred,
                target,
                one_hot_target,
                weight,
                keep_loss_num_ratio = self.keep_loss_num_ratio,
                gamma=self.gamma,
                alpha=self.alpha,
                class_weight=self.class_weight,
                valid_mask=valid_mask,
                reduction=reduction,
                avg_factor=avg_factor)

            if reduction == 'none':
                # [N, C] -> [C, N]
                loss_cls = loss_cls.transpose(0, 1)
                # [C, N] -> [C, B, d1, d2, ...]
                # original_shape: [B, C, /root/autodl-pub/CZX/mmsegmentation_czx/work_dirs/segnext_mscan_-l_2xb4-adamw-foreground_semantic_loss-40k_seafog_3band-600*600_neck_channel_attention_cascade_decode_auhead_3d1, d2, ...]
                loss_cls = loss_cls.reshape(original_shape[1],
                                            original_shape[0],
                                            *original_shape[2:])
                # [C, B, d1, d2, ...] -> [B, C, d1, d2, ...]
                loss_cls = loss_cls.transpose(0, 1).contiguous()
        else:
            raise NotImplementedError
        return loss_cls

    @property
    def loss_name(self):
        """Loss Name.

        This function must be implemented and will return the name of this
        loss function. This name will be used to combine different loss items
        by simple sum operation. In addition, if you want this loss item to be
        included into the backward graph, `loss_` must be the prefix of the
        name.
        Returns:
            str: The name of this loss item.
        """
        return self._loss_name