"""
.. module:: evaluator
    :synopsis: evaluator for sequence labeling
 
"""
import sys
import torch
import numpy as np
import itertools

import model_seq.utils as utils
from torch.autograd import Variable

from ipdb import set_trace

class eval_batch:
    """
    Base class for evaluation, provide method to calculate f1 score and accuracy.

    Parameters
    ----------
    decoder : ``torch.nn.Module``, required.
        the decoder module, which needs to contain the ``to_span()`` method.
    """
    def __init__(self, decoder, gw_map, y_map):
        self.decoder = decoder
        self.gw_map = gw_map
        self.y_map = y_map

    def reset(self):
        """
        reset counters.
        """
        self.correct_labels = 0
        self.total_labels = 0
        self.gold_count = 0
        self.guess_count = 0
        self.overlap_count = 0

    def calc_f1_batch(self, decoded_data, target_data, f_w, file_handler):
        """
        update statics for f1 score.

        Parameters
        ----------
        decoded_data: ``torch.LongTensor``, required.
            the decoded best label index pathes.
        target_data:  ``torch.LongTensor``, required.
            the golden label index pathes.
        """
        batch_decoded = torch.unbind(decoded_data, 1)
        batch_tokens = torch.unbind(f_w, 1)

        for decoded, target, tokens in zip(batch_decoded, target_data, batch_tokens):
            length = len(target)
            best_path = decoded[:length]

            if file_handler != None:
                tokens = tokens[:length]
                for w, p, t in zip(tokens.cpu().numpy(), best_path.cpu().numpy(), target):
                    file_handler.write(self.gw_map[w]+' '+self.y_map[t]+' '+self.y_map[p]+'\n')
                file_handler.write('\n')


            correct_labels_i, total_labels_i, gold_count_i, guess_count_i, overlap_count_i = self.eval_instance(best_path.numpy(), target)
            self.correct_labels += correct_labels_i
            self.total_labels += total_labels_i
            self.gold_count += gold_count_i
            self.guess_count += guess_count_i
            self.overlap_count += overlap_count_i

    def calc_f1_batch_trainset(self, decoded_data, target_data, f_w, a_m, file_handler, allset=False):
        """
        update statics for f1 score.

        Parameters
        ----------
        decoded_data: ``torch.LongTensor``, required.
            the decoded best label index pathes.
        target_data:  ``torch.LongTensor``, required.
            the golden label index pathes.
        """
        batch_decoded = torch.unbind(decoded_data, 1)
        batch_tokens = torch.unbind(f_w, 1)

        for decoded, target, tokens, mask in zip(batch_decoded, target_data, batch_tokens, a_m):
            length = len(target)
            if mask == 0 and allset == False:
                if file_handler != None:
                    tokens = tokens[:length]
                    for w, t in zip(tokens.cpu().numpy(), target):
                        file_handler.write(self.gw_map[w]+' <unk> '+self.y_map[t]+'\n')
                    file_handler.write('\n')
            else:
                best_path = decoded[:length]

                if file_handler != None:
                    tokens = tokens[:length]
                    for w, p, t in zip(tokens.cpu().numpy(), best_path.cpu().numpy(), target):
                        line = self.gw_map[w]+' '+self.y_map[t]+' '+self.y_map[p]
                        file_handler.write(line+'\n')
                    file_handler.write('\n')

                correct_labels_i, total_labels_i, gold_count_i, guess_count_i, overlap_count_i = self.eval_instance(best_path.numpy(), target)
                self.correct_labels += correct_labels_i
                self.total_labels += total_labels_i
                self.gold_count += gold_count_i
                self.guess_count += guess_count_i
                self.overlap_count += overlap_count_i

    def calc_acc_batch(self, decoded_data, target_data):
        """
        update statics for accuracy score.

        Parameters
        ----------
        decoded_data: ``torch.LongTensor``, required.
            the decoded best label index pathes.
        target_data:  ``torch.LongTensor``, required.
            the golden label index pathes.
        """
        batch_decoded = torch.unbind(decoded_data, 1)

        for decoded, target in zip(batch_decoded, target_data):
            
            # remove padding
            length = len(target)
            best_path = decoded[:length].numpy()

            self.total_labels += length
            self.correct_labels += np.sum(np.equal(best_path, gold))

    def f1_score(self):
        """
        calculate the f1 score based on the inner counter.
        """
        if self.guess_count == 0:
            return 0.0, 0.0, 0.0, 0.0
        precision = self.overlap_count / float(self.guess_count)
        recall = self.overlap_count / float(self.gold_count)
        if precision == 0.0 or recall == 0.0:
            return 0.0, 0.0, 0.0, 0.0
        f = 2 * (precision * recall) / (precision + recall)
        accuracy = float(self.correct_labels) / self.total_labels
        return f, precision, recall, accuracy

    def acc_score(self):
        """
        calculate the accuracy score based on the inner counter.
        """
        if 0 == self.total_labels:
            return 0.0
        accuracy = float(self.correct_labels) / self.total_labels
        return accuracy        

    def eval_instance(self, best_path, gold):
        """
        Calculate statics to update inner counters for one instance.

        Parameters
        ----------
        best_path: required.
            the decoded best label index pathe.
        gold: required.
            the golden label index pathes.
      
        """
        total_labels = len(best_path)
        correct_labels = np.sum(np.equal(best_path, gold))
        gold_chunks = self.decoder.to_spans(gold)
        gold_count = len(gold_chunks)

        guess_chunks = self.decoder.to_spans(best_path)
        guess_count = len(guess_chunks)

        overlap_chunks = gold_chunks & guess_chunks
        overlap_count = len(overlap_chunks)

        return correct_labels, total_labels, gold_count, guess_count, overlap_count

class eval_wc:
    """
    evaluation class for LD-Net

    Parameters
    ----------
    decoder : ``torch.nn.Module``, required.
        the decoder module, which needs to contain the ``to_span()`` and ``decode()`` method.
    score_type : ``str``, required.
        whether the f1 score or the accuracy is needed.
    """
    def __init__(self, decoder, score_type, a_num, gw_map, y_map):
        self.decoder = decoder
        self.a_num = a_num
        self.eval_batch = [eval_batch(decoder, gw_map, y_map) for i in range(self.a_num)]

        if 'f' in score_type:
            self.eval_b = [eval_b.calc_f1_batch for eval_b in self.eval_batch]
            self.calc_s = [eval_b.f1_score for eval_b in self.eval_batch]
        else:
            self.eval_b = [eval_b.calc_acc_batch for eval_b in self.eval_batch]
            self.calc_s = [eval_b.acc_score for eval_b in self.eval_batch]

    def calc_score(self, seq_model, dataset_loader, save_path=None):
        """
        calculate scores

        Parameters
        ----------
        seq_model: required.
            sequence labeling model.
        dataset_loader: required.
            the dataset loader.

        Returns
        -------
        score: ``float``.
            calculated score.
        """
        seq_model.eval()
        for eval_b in self.eval_batch:
            eval_b.reset()

        if save_path != None:
            output_file = [open(save_path+'_'+str(idx), 'w') for idx in range(self.a_num)]
        else:
            output_file = [None for idx in range(self.a_num)]

        for f_c, f_p, b_c, b_p, f_w, _, f_y_m, g_y in dataset_loader:
            scores = seq_model(f_c, f_p, b_c, b_p, f_w)
            #decoded = torch.stack([self.decoder.decode(score, f_y_m) for score in scores.data])
            for idx, score in enumerate(scores.data):
                decoded = self.decoder.decode(score, f_y_m)
                self.eval_b[idx](decoded, g_y, f_w, output_file[idx])

        return [self.calc_s[i]() for i in range(self.a_num)]

class eval_wc_latent(eval_batch):
    """
    evaluation class for LD-Net

    Parameters
    ----------
    decoder : ``torch.nn.Module``, required.
        the decoder module, which needs to contain the ``to_span()`` and ``decode()`` method.
    score_type : ``str``, required.
        whether the f1 score or the accuracy is needed.
    """
    def __init__(self, decoder, score_type, gw_map, y_map):
        eval_batch.__init__(self, decoder, gw_map, y_map)
        self.gw_map = gw_map
        self.y_map = y_map

        if 'f' in score_type:
            self.eval_b = self.calc_f1_batch
            self.calc_s = self.f1_score
        else:
            self.eval_b = self.calc_acc_batch
            self.calc_s = self.acc_score

    def calc_score(self, seq_model, dataset_loader, save_path=None):
        """
        calculate scores

        Parameters
        ----------
        seq_model: required.
            sequence labeling model.
        dataset_loader: required.
            the dataset loader.

        Returns
        -------
        score: ``float``.
            calculated score.
        """
        seq_model.eval()
        self.reset()

        if save_path != None:
            output_file = open(save_path, 'w')
        else:
            output_file = None

        for f_c, f_p, b_c, b_p, f_w, _, f_y_m, g_y in dataset_loader:
            scores = seq_model.latent_forward(f_c, f_p, b_c, b_p, f_w)
            decoded = self.decoder.decode(scores.data, f_y_m)
            self.eval_b(decoded, g_y, f_w, output_file)

        return self.calc_s()

class eval_wc_trainset:
    """
    evaluation class for LD-Net

    Parameters
    ----------
    decoder : ``torch.nn.Module``, required.
        the decoder module, which needs to contain the ``to_span()`` and ``decode()`` method.
    score_type : ``str``, required.
        whether the f1 score or the accuracy is needed.
    """
    def __init__(self, decoder, score_type, a_num, gw_map, y_map):
        self.decoder = decoder
        self.a_num = a_num
        self.eval_batch = [eval_batch(decoder, gw_map, y_map) for i in range(self.a_num)]

        if 'f' in score_type:
            self.eval_b = [eval_b.calc_f1_batch_trainset for eval_b in self.eval_batch]
            self.calc_s = [eval_b.f1_score for eval_b in self.eval_batch]
        else:
            self.eval_b = [eval_b.calc_acc_batch for eval_b in self.eval_batch]
            self.calc_s = [eval_b.acc_score for eval_b in self.eval_batch]

    def calc_score(self, seq_model, dataset_loader, save_path=None, allset=False):
        """
        calculate scores

        Parameters
        ----------
        seq_model: required.
            sequence labeling model.
        dataset_loader: required.
            the dataset loader.

        Returns
        -------
        score: ``float``.
            calculated score.
        """
        seq_model.eval()
        for eval_b in self.eval_batch:
            eval_b.reset()

        if save_path != None:
            output_file = [open(save_path+'_'+str(idx), 'w') for idx in range(self.a_num)]
        else:
            output_file = [None for idx in range(self.a_num)]

        for f_c, f_p, b_c, b_p, f_w, _, f_y_m, a_m, g_y in dataset_loader:
            scores = seq_model(f_c, f_p, b_c, b_p, f_w)
            #decoded = torch.stack([self.decoder.decode(score, f_y_m) for score in scores.data])
            targets = list()
            for i in range(self.a_num):
                target = list()
                for j in range(len(g_y)):
                    target.append([g_y[j][k][i] for k in range(len(g_y[j]))])
                targets.append(target)

            for idx, score in enumerate(scores.data):
                decoded = self.decoder.decode(score, f_y_m)

                self.eval_b[idx](decoded, targets[idx], f_w, a_m[idx], output_file[idx], allset=allset)


        return [self.calc_s[i]() for i in range(self.a_num)]

