import pdb
import copy
from itertools import product
import datetime
import logging
from IPython.core.debugger import Tracer

from . import officer
from . import setup_environment
from . import experiment
from .features import class_map
from .features import officers

log = logging.getLogger(__name__)

try:
    log.info("Connecting to database...")
    engine, _ = setup_environment.get_database()
except:
    log.error('Could not connect to the database')
    
def create_features_table(config, table_name):
    """Build the features table for the type of model (officer/dispatch) specified in the config file"""

    if config['unit'] == 'officer':
        create_officer_features_table(config, table_name)
    if config['unit'] == 'dispatch':
        create_dispatch_features_table(config, table_name)


def populate_features_table(config, table_name):
    """Calculate values for all features which are set to True (in the config file) 
    for the appropriate run type (officer/dispatch)
    """

    if config['unit'] == 'officer':
        populate_officer_features_table(config, table_name)
    if config['unit'] == 'dispatch':
        populate_dispatch_features_table(config, table_name)


def create_officer_features_table(config, table_name="officer_features"):
    """ Creates a features.table_name table within the features schema """

    # drop the old features table
    log.info("Dropping the old officer feature table: {}".format(table_name))
    engine.execute("DROP TABLE IF EXISTS features.{}".format(table_name) )

    # get a list of table column names.
    column_names = officer.get_officer_features_table_columns( config )

    # Get a list of all the features that are set to true.
    features = config["officer_features"]
    feature_list = [ key for key in features if features[key] == True ]
    feature_value = [True]*len(feature_list)

    # make sure we have at least 1 feature
    assert len(feature_list) > 0, 'List of features to build is empty'

    # use the appropriate id column, depending on feature types (officer / dispatch)
    id_column = '{}_id'.format(config['unit'])

    # Create and execute a query to create a table with a column for each of the features.
    log.info("Creating new officer feature table: {}...".format(table_name))
    create_query = (    "CREATE TABLE features.{} ( "
                        "   {}              int, "
                        "   created_on      timestamp, "
                        "   fake_today      timestamp, "
                        .format(
                            table_name,
                            id_column))

    # create a column for all the features we'll generate.
    feature_query = ', '.join(["{} numeric ".format(x) for x in column_names])

    final_query = create_query + feature_query + ");"

    engine.execute(final_query)

    # Get the list of fake_todays.
    temporal_info = experiment.generate_time_info(config)
    fake_todays = {time_dict['fake_today'] for time_dict in temporal_info}

    # Populate the features table with officer_id.
    log.info("Populating feature table {} with officer ids and fake todays...".format(table_name))
    time_format = "%Y-%m-%d %X"
    for fake_today in fake_todays:
        fake_today = datetime.datetime.strptime(fake_today, '%d%b%Y') 
        fake_today.strftime(time_format)
        officer_id_query = (    "INSERT INTO features.{} (officer_id, created_on, fake_today) "
                                "SELECT staging.officers_hub.officer_id, '{}'::timestamp, '{}'::date "
                                "FROM staging.officers_hub").format(    table_name,
                                                                        datetime.datetime.now(),
                                                                        fake_today)
        engine.execute(officer_id_query)


def create_dispatch_features_table(config, table_name="dispatch_features"):

    # drop the old features table
    log.info("Dropping the old dispatch feature table: {}".format(table_name))
    engine.execute("DROP TABLE IF EXISTS features.{}".format(table_name))

    # Get a list of all the features that are set to true.
    feature_list = [feat for feat, is_set_true in config['dispatch_features'].items() if is_set_true]

    # make sure we have at least 1 feature
    assert len(feature_list) > 0, 'List of features to build is empty'

    # use the appropriate id column, depending on feature types (officer / dispatch)
    id_column = '{}_id'.format(config['unit'])

    # Create and execute a query to create a table with a column for each of the features.
    log.info("Creating new dispatch feature table: {}".format(table_name))

    create_query = (    "CREATE TABLE features.{} ( "
                        "   {}              varchar(20), "
                        "   created_on      timestamp"
                        .format(
                            table_name,
                            id_column))

    # add a column for each categorical feature in feature_list
    cat_features = class_map.find_categorical_features(feature_list)
    cat_feature_query = ', '.join(["{} varchar(20) ".format(x) for x in cat_features])

    # add a column for each numeric feature in feature_list
    num_features = set(feature_list) - set(cat_features)
    num_feature_query = ', '.join(["{} numeric ".format(x) for x in num_features])

    final_query = ', '.join([create_query, num_feature_query, cat_feature_query]) + ");"
    engine.execute(final_query)

    # TODO: for dispatch predictions we need to figure out an alternative to fake_today
    #       temporal cross validation

    # Populate the features table with dispatch id.
    log.info("Populating feature table {} with dispatch ids ".format(table_name))

    query = (   "INSERT INTO features.{} "
                "({}) "
                "SELECT DISTINCT "
                "staging.events_hub.dispatch_id "
                "FROM staging.events_hub"
                .format(
                    table_name,
                    id_column))

    engine.execute(query)


def populate_dispatch_features_table(config, table_name):
    """Calculate all the feature values and store them in the features table in the database"""

    # Get a list of all the features that are set to true.
    feature_list = [feat for feat, is_set_true in config['dispatch_features'].items() if is_set_true]

    for feature_name in feature_list:

       feature_class = class_map.lookup(feature_name, 
										unit = 'dispatch',
                                        fake_today = datetime.datetime.today(),
                                        table_name = table_name)

       log.debug('Calculating and inserting feature {}'.format(feature_class.feature_name))

       feature_class.build_and_insert(engine)


def populate_officer_features_table(config, table_name):
    """Calculate all the feature values and store them in the features table in the database"""

    # get the list of fake todays specified by the config file
    temporal_info = experiment.generate_time_info(config)

    # using a set comprehension to remove duplicates, bc temporal_info gives multiple time windows
    # which we don't care about here
    fake_todays = {time_dict['fake_today'] for time_dict in temporal_info}

    # get a list of all features that are set to true.
    active_features = [ key for key in config["officer_features"] if config["officer_features"][key] == True ] 

    # loop over all fake todays, populating the active features for each.
    for feature_name in active_features:
        for fake_today in fake_todays:
            feature_class = class_map.lookup(feature_name, 
											 unit = 'officer',
                                             fake_today=datetime.datetime.strptime(fake_today, "%d%b%Y" ),
                                             table_name=table_name, 
                                             lookback_durations=config["timegated_feature_lookback_duration"])
            feature_class.build_and_insert(engine)
            log.debug('Calculated and inserted feature {} for fake_today {}'
                        .format(feature_class.feature_name, fake_today))