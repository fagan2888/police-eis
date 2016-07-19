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

def drop_and_load_features_schema():
    """ If the features schema exists, DROP and CREATE.  If it doesn't, CREATE """

    # Create the schema.
    log.info("Connecting to database...")
    engine, db_config = setup_environment.get_database()
    log.info("Dropping the old features schema...")
    engine.execute("DROP SCHEMA IF EXISTS features CASCADE") # Note: this should be confirmed by the user before dropping the features.
    engine.execute("CREATE SCHEMA features") 

def create_features_table(config, table_name="features" ):
    """ Creates a features.table_name table within the features schema """

    log.info("Re-building features...")

    # Drop the table and rebuild.
    log.info("Connecting to database...")
    engine, db_config = setup_environment.get_database()
    db_conn = engine.raw_connection()
    log.info("Dropping the old feature table...")
    db_conn.cursor().execute("DROP TABLE IF EXISTS features.{}".format(table_name) )

    # Get a list of all the features.
    feature_classes = config["features"]
    feature_list  = []
    feature_value = []
    #for classkey in feature_classes:
    #    feature_list.extend(feature_classes[classkey].keys())
    #    feature_value.extend(feature_classes[classkey].values())
    feature_list.extend( feature_classes["arrests"].keys() )
    feature_value.extend( feature_classes["arrests"].values() )

    # Split the height_weight feature into two features.
    if "height_weight" in feature_list:
        feature_list.extend(["height","weight"])
        feature_list.remove("height_weight")

    # Create and execute a query to create a table with a column for each of the features.
    log.info("Createing new feature table: {}...".format(table_name))
    create_query = "CREATE TABLE features.{} ( \n".format(table_name)
    create_query += "\t officer_id \t int,\n"
    create_query += "\t created_on \t timestamp,\n"
    create_query += "\t fake_today \t timestamp,\n"
    feature_query = [ "\t {} \t numeric \n".format(x) for x in feature_list ]
    create_query += ', '.join(feature_query)
    create_query += ");"
    engine.execute( create_query )


def populate_features_table(config):
    """Calculate all the feature values and store them in the features table in the database"""

    # connect to the database
    log.info("Connecting to database...")
    engine, db_config = setup_environment.get_database()

    # get the list of fake todays specified by the config file
    temporal_info = experiment.generate_time_info(config)

    # using set to remove duplicates, bc temporal_info gives multiple time windows
    # which we don't care about here
    fake_todays = {time_dict['fake_today'] for time_dict in temporal_info}

    # loop through the feature groups
    #for feature_group in config['features']:

        # select each feature in the group individually
        #for feature_name in config['features'][feature_group]:

    # NOTE: just for debugging
    for feature_name in config['features']['arrests']:

        # loop over each fake today
        for fake_today in fake_todays:

            feature_class = class_map.lookup(feature_name, time_bound=datetime.datetime.strptime(fake_today, "%d%b%Y" ))
            #engine.execute(feature_class.query)
            log.debug('Calculated and inserted feature {} for fake_today {}'
                        .format(feature_class.feature_name, fake_today))
