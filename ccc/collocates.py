#! /usr/bin/env python
# -*- coding: utf-8 -*-

from itertools import chain
# part of module
from .utils import node2cooc, fold_df
# requirements
from pandas import DataFrame
from association_measures.measures import calculate_measures
import association_measures.frequencies as fq
# logging
import logging
logger = logging.getLogger(__name__)


class Collocates:
    """ collocation analysis """

    def __init__(self, corpus, df_dump, p_query, mws=10):

        # consistency check
        if len(df_dump) == 0:
            logger.warning('cannot calculate collocates of 0 contexts')
            return

        # TODO: start independent CQP process
        self.corpus = corpus

        # what's in the dump?
        self.df_dump = df_dump
        self.size = len(df_dump)

        # maximum window size (=context)
        self.mws = mws

        # determine layer to work on
        if p_query not in self.corpus.attributes_available['name'].values:
            logger.warning(
                'p_att "%s" not available, falling back to primary layer' % p_query
            )
            p_query = 'word'
        self.p_query = p_query

        # collect context and save result
        logger.info('collecting contexts')
        deflated, f1_set = df_node_to_cooc(self.df_dump)
        logger.info('collected %d token positions' % len(deflated))
        self.deflated = deflated
        self.f1_set = f1_set

    def count(self, window):

        mws = self.mws
        if window > mws:
            logger.warning(
                'requested window outside maximum window size,'
                ' falling back to %d' % mws
            )
            window = mws

        # slice relevant window
        relevant = self.deflated.loc[abs(self.deflated['offset']) <= window]

        # number of possible occurrence positions within window
        f1_inflated = len(relevant)

        # get frequency counts
        counts = self.corpus.counts.cpos(
            relevant['cpos'], [self.p_query]
        )
        counts.columns = ['f']
        counts.index = counts.index.get_level_values(self.p_query)

        return counts, f1_inflated

    def show(self, window=5, order='f', cut_off=100, ams=None,
             min_freq=2, frequencies=True, flags=None):

        # consistency check
        if len(self.f1_set) == 0:
            logger.error("nothing to show")
            return DataFrame()

        # get frequencies
        f, f1_inflated = self.count(window)

        # get marginals
        f2 = self.corpus.marginals(
            f.index, self.p_query
        )
        f2.columns = ['marginal']

        # deduct node frequencies from marginals
        node_freq = self.corpus.counts.cpos(self.f1_set, [self.p_query])
        node_freq.index = node_freq.index.get_level_values(self.p_query)
        node_freq.columns = ['in_nodes']
        f2 = f2.join(node_freq)
        f2 = f2.fillna(0)
        f2['in_nodes'] = f2['in_nodes'].astype(int)
        f2['f2'] = f2['marginal'] - f2['in_nodes']

        # get sub-corpus size
        f1 = f1_inflated

        # get corpus size
        N = self.corpus.corpus_size - len(self.f1_set)

        collocates = add_ams(
            f, f1, f2, N,
            min_freq, order, cut_off, flags, ams, frequencies
        )

        return collocates


# utilities ####################################################################
def df_node_to_cooc(df_dump, context=None):
    """ converts df_dump to df_cooc

    df_node: [match, matchend] + [context_id, context, contextend]
    df_cooc: [match, cpos, offset] (dedpulicated)
    f1_set: cpos of nodes

    deduplication strategy:
    (1a) create overlapping contexts with nodes
    (1b) concatenate local contexts
    (2a) sort by abs(offset)
    (2b) deduplicate by cpos, keep first occurrences (=smallest offset)
    (3a) f1_set = (cpos where offset == 0)
    (3b) remove rows where cpos in f1_set

    NB: equivalent to UCS when switching steps 3a and 3b
    """

    # can't work on 0 context
    if context == 0:
        return DataFrame(), set()

    # reset the index to be able to work with it
    df = df_dump.reset_index()

    if context is None:
        if (
            df['match'].values == df['context'].values
        ).all() and (
            df['matchend'].values == df['contextend'].values
        ).all():
            return DataFrame(), set()
        else:
            df['start'] = df['context']
            df['end'] = df['contextend']

    else:
        logger.info("re-confine regions by given context")
        df['start'] = df['match'] - context
        df['start'] = df[['start', 'context']].max(axis=1)
        df['end'] = df['matchend'] + context
        df['end'] = df[['end', 'contextend']].min(axis=1)

    logger.info("(1a) create local contexts")
    df = DataFrame.from_records(df.apply(node2cooc, axis=1).values)

    logger.info("(1b) concatenate local contexts")
    df_infl = DataFrame({
        'match': list(chain.from_iterable(df['match_list'].values)),
        'cpos': list(chain.from_iterable(df['cpos_list'].values)),
        'offset': list(chain.from_iterable(df['offset_list'].values))
    })

    logger.info("(2a) sort by absolute offset")
    df_infl['abs_offset'] = df_infl.offset.abs()
    df_infl = df_infl.sort_values(by=['abs_offset', 'cpos'])
    df_infl = df_infl.drop(["abs_offset"], axis=1)

    logger.info("(2b) drop duplicates")
    df_defl = df_infl.drop_duplicates(subset='cpos')

    logger.info("(3a) identify nodes ...")
    f1_set = set(df_defl.loc[df_defl['offset'] == 0]['cpos'])

    logger.info("(3b) ... and remove them")
    df_defl = df_defl[df_defl['offset'] != 0]

    return df_defl, f1_set


def add_ams(f, f1, f2, N,
            min_freq=2,
            order='f',
            cut_off=100,
            flags=None,
            ams=None,
            frequencies=True):

    # drop items that occur less than min-freq
    f = f.loc[~(f['f'] < min_freq)]

    # init contingency table with f and f2
    contingencies = f.join(f2)

    # post-processing: fold items
    contingencies = fold_df(contingencies, flags)

    # add constant columns
    contingencies['N'] = N
    contingencies['f1'] = f1
    # NB: frequency signature notation (Evert 2004: 36)

    # add measures
    logger.info("calculating measures")
    measures = calculate_measures(contingencies, ams)
    contingencies = contingencies.join(measures)

    # create output
    if frequencies:
        contingencies = contingencies.join(
            fq.observed_frequencies(contingencies)
        )
        contingencies = contingencies.join(
            fq.expected_frequencies(contingencies)
        )
    contingencies.index.name = 'item'

    # sort dataframe
    contingencies.sort_values(
        by=[order, 'item'],
        ascending=False, inplace=True
    )

    if cut_off is not None:
        contingencies = contingencies.head(cut_off)

    return contingencies
