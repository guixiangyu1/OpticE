#!/usr/bin/python3

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import torch
import math

from torch.utils.data import Dataset

class TrainDataset(Dataset):
    def __init__(self, triples, nentity, nrelation, negative_sample_size, mode, step):
        self.len = len(triples)
        self.triples = triples
        self.triple_set = set(triples)
        self.nentity = nentity
        self.nrelation = nrelation
        self.negative_sample_size = negative_sample_size
        self.mode = mode
        self.count = self.count_frequency(triples)
        self.true_head, self.true_tail, self.tph, self.hpt = self.get_true_head_and_tail(self.triples)
        self.step = step

    def __len__(self):
        return self.len

    def __getitem__(self, idx):
        thre = 2
        positive_sample = self.triples[idx]

        head, relation, tail = positive_sample

        subsampling_weight = self.count[(head, relation)] + self.count[(tail, -relation - 1)]
        subsampling_weight = torch.sqrt(1 / torch.Tensor([subsampling_weight]))

        # pr4head = self.tph[relation] / (self.hpt[relation] + self.tph[relation])

        if self.hpt[relation] < self.tph[relation]:
            freq = 1 + self.tph[relation] / self.hpt[relation]
            freq = math.floor(freq)
            if freq > thre:
                freq = thre
            if self.step % freq == 0:
                self.mode = 'head-batch'
                sign = torch.Tensor([-1])
                positive_entity = tail
                replaced_entity = head
            else:
                self.mode = 'tail-batch'
                sign = torch.Tensor([1])
                positive_entity = head
                replaced_entity = tail

        else:
            freq = 1 + self.hpt[relation] / self.tph[relation]
            freq = math.floor(freq)
            if freq > thre:
                freq = thre
            if self.step % freq == 0:
                self.mode = 'tail-batch'
                sign = torch.Tensor([1])
                positive_entity = head
                replaced_entity = tail
            else:
                self.mode = 'head-batch'
                sign = torch.Tensor([-1])
                positive_entity = tail
                replaced_entity = head

        negative_sample_list = []
        negative_sample_size = 0

        while negative_sample_size < self.negative_sample_size:
            negative_sample = np.random.randint(self.nentity, size=self.negative_sample_size * 2)
            if self.mode == 'head-batch':
                mask = np.in1d(
                    negative_sample,
                    self.true_head[(relation, tail)],
                    assume_unique=True,
                    invert=True
                )
            elif self.mode == 'tail-batch':
                mask = np.in1d(
                    negative_sample,
                    self.true_tail[(head, relation)],
                    assume_unique=True,
                    invert=True
                )
            else:
                raise ValueError('Training batch mode %s not supported' % self.mode)
            negative_sample = negative_sample[mask]
            negative_sample_list.append(negative_sample)
            negative_sample_size += negative_sample.size

        negative_sample = np.concatenate(negative_sample_list)[:self.negative_sample_size]

        negative_sample = torch.from_numpy(negative_sample)

        # positive_sample = torch.LongTensor(positive_sample)
        positive_entity = torch.LongTensor([positive_entity])
        replaced_entity = torch.LongTensor([replaced_entity])
        relation = torch.LongTensor([relation])

        return positive_entity, replaced_entity, relation, negative_sample, subsampling_weight, sign, self.mode

    @staticmethod
    def collate_fn(data):
        positivE = torch.cat([_[0] for _ in data], dim=0)
        replaceE = torch.cat([_[1] for _ in data], dim=0)
        relation = torch.cat([_[2] for _ in data], dim=0)
        negative_sample = torch.stack([_[3] for _ in data], dim=0)
        subsampling_weight = torch.cat([_[4] for _ in data], dim=0)
        sign = torch.cat([_[5] for _ in data], dim=0)
        mode = data[0][6]
        return positivE, replaceE, relation, negative_sample, subsampling_weight, sign, mode

    @staticmethod
    def count_frequency(triples, start=4):
        '''
        Get frequency of a partial triple like (head, relation) or (relation, tail)
        The frequency will be used for subsampling like word2vec
        '''
        count = {}
        for head, relation, tail in triples:
            if (head, relation) not in count:
                count[(head, relation)] = start
            else:
                count[(head, relation)] += 1

            if (tail, -relation - 1) not in count:
                count[(tail, -relation - 1)] = start
            else:
                count[(tail, -relation - 1)] += 1
        return count

    @staticmethod
    def get_true_head_and_tail(triples):
        '''
        Build a dictionary of true triples that will
        be used to filter these true triples for negative sampling
        '''

        true_head = {}
        true_tail = {}
        tph = {}
        hpt = {}
        head_num = {}
        tail_num = {}

        for head, relation, tail in triples:
            if (head, relation) not in true_tail:
                true_tail[(head, relation)] = []
            true_tail[(head, relation)].append(tail)
            if (relation, tail) not in true_head:
                true_head[(relation, tail)] = []
            true_head[(relation, tail)].append(head)

        for relation, tail in true_head:
            true_head[(relation, tail)] = np.array(list(set(true_head[(relation, tail)])))
        for head, relation in true_tail:
            true_tail[(head, relation)] = np.array(list(set(true_tail[(head, relation)])))


        # calculate hpt and tph
        for head, relation in true_tail:
            if relation not in head_num:
                head_num[relation] = 0
                tail_num[relation] = 0
            head_num[relation] += 1
            tail_num[relation] += len(true_tail[(head, relation)])
        for relation in head_num:
            tph[relation] = tail_num[relation] / head_num[relation]

        head_num = {}
        tail_num = {}
        for relation, tail in true_head:
            if relation not in tail_num:
                tail_num[relation] = 0
                head_num[relation] = 0
            head_num[relation] += len(true_head[(relation, tail)])
            tail_num[relation] += 1
        for relation in tail_num:
            hpt[relation] = head_num[relation] / tail_num[relation]

        return true_head, true_tail, tph, hpt


class TestDataset(Dataset):
    def __init__(self, triples, all_true_triples, nentity, nrelation, mode):
        self.len = len(triples)
        self.triple_set = set(all_true_triples)
        self.triples = triples
        self.nentity = nentity
        self.nrelation = nrelation
        self.mode = mode

    def __len__(self):
        return self.len

    def __getitem__(self, idx):
        head, relation, tail = self.triples[idx]

        if self.mode == 'head-batch':
            tmp = [(0, rand_head) if (rand_head, relation, tail) not in self.triple_set
                   else (-100, head) for rand_head in range(self.nentity)]
            tmp[head] = (0, head)
            replaced_entity = head
            positive_entity = tail
            sign = torch.Tensor([-1])
        elif self.mode == 'tail-batch':
            tmp = [(0, rand_tail) if (head, relation, rand_tail) not in self.triple_set
                   else (-100, tail) for rand_tail in range(self.nentity)]
            tmp[tail] = (0, tail)
            replaced_entity = tail
            positive_entity = head
            sign = torch.Tensor([1])
        else:
            raise ValueError('negative batch mode %s not supported' % self.mode)

        tmp = torch.LongTensor(tmp)
        filter_bias = tmp[:, 0].float()
        negative_sample = tmp[:, 1]

        positive_entity = torch.LongTensor([positive_entity])
        replaced_entity = torch.LongTensor([replaced_entity])
        relation = torch.LongTensor([relation])

        return positive_entity, replaced_entity, relation, negative_sample, filter_bias, sign, self.mode

    @staticmethod
    def collate_fn(data):
        positivE = torch.cat([_[0] for _ in data], dim=0)
        replaceE = torch.cat([_[1] for _ in data], dim=0)
        relation = torch.cat([_[2] for _ in data], dim=0)
        negative_sample = torch.stack([_[3] for _ in data], dim=0)
        filter_bias = torch.stack([_[4] for _ in data], dim=0)
        sign = torch.cat([_[5] for _ in data], dim=0)
        mode = data[0][6]
        return positivE, replaceE, relation, negative_sample, filter_bias, sign, mode


class BidirectionalOneShotIterator(object):
    def __init__(self, dataloader1, dataloader2):
        self.iterator1 = self.one_shot_iterator(dataloader1)
        self.iterator2 = self.one_shot_iterator(dataloader2)
        self.step = 0

    def __next__(self):
        self.step += 1
        if self.step % 2 == 1:
            data = next(self.iterator1)
        else:
            assert self.step % 2 == 0
            data = next(self.iterator2)
        return data

    @staticmethod
    def one_shot_iterator(dataloader):
        '''
        Transform a PyTorch Dataloader into python iterator
        '''
        while True:
            for data in dataloader:
                yield data
