import numpy as np
import pdb
import pandas as pd
import yaml
import logging
import sys
import datetime

from eis import setup_environment
from eis.features import officers as featoff


log = logging.getLogger(__name__)


def convert_categorical(df):
    """
    this function generates features from a nominal feature

    Inputs:
    df: a dataframe with two columns: id, and a feature which is 1
    of n categories

    Outputs:
    df: a dataframe with 1 + n columns: id and boolean features that are
    "category n" or not
    """

    onecol = df.columns[0]
    categories = pd.unique(df[onecol])

    # Remove empty fields
    # Replace Nones or empty fields with NaNs?
    categories = [x for x in categories if x is not None]
    try:
        categories.remove(' ')
    except:
        pass

    # Get rid of capitalization differences
    categories = list(set([str.lower(x) for x in categories]))

    # Set up new features
    featnames = []
    if len(categories) == 2:
        newfeatstr = 'is_' + categories[0]
        featnames.append(newfeatstr)
        df[newfeatstr] = df[onecol] == categories[0]
    else:
        for i in range(len(categories)):
            if type(categories[i]) is str:
                newfeatstr = 'is_' + categories[i]
                featnames.append(newfeatstr)
                df[newfeatstr] = df[onecol] == categories[i]

    df = df.drop(onecol, axis=1)
    return df.astype(int), list(df.columns)


def lookup(feature, **kwargs):

    class_lookup = {'height_weight': featoff.OfficerHeightWeight(**kwargs),
                    'education': featoff.OfficerEducation(**kwargs),
                    'ia_history': featoff.IAHistory(**kwargs),
                    'yearsexperience': featoff.OfficerYrsExperience(**kwargs),
                    'daysexperience': featoff.OfficerDaysExperience(**kwargs),
                    'malefemale': featoff.OfficerMaleFemale(**kwargs),
                    'race': featoff.OfficerRace(**kwargs),
                    'officerage': featoff.OfficerAge(**kwargs),
                    'officerageathire': featoff.OfficerAgeAtHire(**kwargs),
                    'maritalstatus': featoff.OfficerMaritalStatus(**kwargs),
                    'careerarrests': featoff.OfficerCareerArrests(**kwargs),
                    'numrecentarrests': featoff.NumRecentArrests(**kwargs),
                    'careerNPCarrests': featoff.CareerNPCArrests(**kwargs),
                    'recentNPCarrests': featoff.RecentNPCArrests(**kwargs),
                    'careerdiscarrests': featoff.CareerDiscretionaryArrests(**kwargs),
                    'recentdiscarrests': featoff.RecentDiscretionaryArrests(**kwargs),
                    'arresttod': featoff.OfficerAvgTimeOfDayArrests(**kwargs),
                    'arresteeage': featoff.OfficerAvgAgeArrests(**kwargs)}

    if feature not in class_lookup.keys():
        raise UnknownFeatureError(feature)

    return class_lookup[feature]


class UnknownFeatureError(Exception):
    def __init__(self, feature):
        self.feature = feature

    def __str__(self):
        return "Unknown feature: {}".format(self.feature)


class FeatureLoader():

    def __init__(self, start_date, end_date, fake_today):

        engine, config = setup_environment.get_database()

        self.con = engine.raw_connection()
        self.con.cursor().execute("SET SCHEMA '{}'".format(config['schema']))
        self.start_date = start_date
        self.end_date = end_date
        self.fake_today = fake_today
        self.tables = config  # Dict of tables
        self.schema = config['schema']

    def officer_labeller(self):
        """
        Load the IDs for a set of officers investigated between
        two dates and the outcomes

        Returns:
        labels: pandas dataframe with two columns:
        newid and adverse_by_ourdef
        """

        log.info("Loading labels...")

        # These are the objects flagged as ones
        query = ("SELECT newid, adverse_by_ourdef from {}.{} "
                 "WHERE dateoccured >= '{}'::date "
                 "AND dateoccured <= '{}'::date"
                 ).format(self.schema, self.tables["si_table"],
                          self.start_date, self.end_date)

        labels = pd.read_sql(query, con=self.con)

        # Now also label those not sampled

        return labels

    def dispatch_labeller(self):
        """
        Load the dispatch events investigated between
        two dates and the outcomes

        Returns:
        labels: pandas dataframe with two columns:
        newid, adverse_by_ourdef, dateoccured
        """

        log.info("Loading labels...")

        # These are the objects flagged as ones and twos
        query = ("SELECT newid, adverse_by_ourdef, "
                 "dateoccured from {}.{} "
                 "WHERE dateoccured >= '{}'::date "
                 "AND dateoccured <= '{}'::date"
                 ).format(self.schema, self.tables["si_table"],
                          self.start_date, self.end_date)

        labels = pd.read_sql(query, con=self.con)

        # Now also label those not sampled
        # Grab all dispatch events and filter out the ones
        # already included

        pdb.set_trace()

        return labels

    def loader(self, features_to_load):
        kwargs = {
            'time_bound': self.fake_today
        }
        feature = lookup(features_to_load, **kwargs)

        results = self.__read_feature_from_db(feature.query,
                                              features_to_load,
                                              drop_duplicates=True)
        featurenames = feature.name_of_features

        if feature.type_of_features == "categorical":
            results, featurenames = convert_categorical(results)

        return results, featurenames

    def __read_feature_from_db(self, query, features_to_load,
                               drop_duplicates=True):

        log.debug("Loading features for events from "
                  "%(start_date)s to %(end_date)s".format(
                        self.start_date, self.end_date))

        results = pd.read_sql(query, con=self.con)

        if drop_duplicates:
            results = results.drop_duplicates(subset=["newid"])

        results = results.set_index(["newid"])
        # features = features[features_to_load]

        log.debug("... {} rows, {} features".format(len(results),
                                                    len(results.columns)))
        return results


def grab_officer_data(features, start_date, end_date, time_bound):
    """
    Function that defines the dataset.

    Inputs:
    -------
    features: dict containing which features to use
    start_date: start date for selecting officers
    end_date: end date for selecting officers
    time_bound: build features with respect to this date
    """

    start_date = start_date.strftime('%Y-%m-%d')
    end_date = end_date.strftime('%Y-%m-%d')
    data = FeatureLoader(start_date, end_date, time_bound)

    officers = data.officer_labeller()
    # officers.set_index(["newid"])

    dataset = officers
    featnames = []
    for each_feat in features:
        if features[each_feat] == True:
            feature_df, names = data.loader(each_feat)
            featnames = featnames + names
            dataset = dataset.join(feature_df, how='left', on='newid')

    dataset = dataset.reset_index()
    dataset = dataset.reindex(np.random.permutation(dataset.index))
    dataset = dataset.set_index(["newid"])

    dataset = dataset.dropna()

    labels = dataset["adverse_by_ourdef"].values
    feats = dataset.drop(["adverse_by_ourdef", "index"], axis=1)
    ids = dataset.index.values

    # Imputation will go here

    log.debug("Dataset has {} rows and {} features".format(
       len(labels), len(feats.columns)))

    return feats, labels, ids, featnames
