import numpy as np
import pandas as pd
import yaml
import logging
import sys
import argparse
import pickle
import datetime

from . import setup_environment, models, scoring
from . import dataset, experiment, groups
from . import populate_features

def main(config_file_name, args):
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        level=logging.DEBUG)
    log = logging.getLogger('eis')

    try:
        with open(config_file_name, 'r') as f:
            config = yaml.load(f)
        log.info("Loaded experiment file: {}".format(config_file_name))
    except:
        log.exception("Failed to get experiment configuration file!")

    # If asked to generate features, then do that and stop.
    if args.buildfeatures:
        
        log.info("Re-building features...")

    	# Create the schema.
        #populate_features.drop_and_load_features_schema()

        # Create the table.
        #populate_features.create_features_table(config, table_name="features") 

        # Populate the schema with features.
        populate_features.populate_features_table(config)

        sys.exit()

    all_experiments = experiment.generate_models_to_run(config)    

    log.info("Running models on dataset...")
    for my_exp in all_experiments:
        timestamp = datetime.datetime.now().isoformat()

        result_y, importances, modelobj, individual_imps = models.run(
            my_exp.exp_data["train_x"],
            my_exp.exp_data["train_y"],
            my_exp.exp_data["test_x"],
            my_exp.config["model"],
            my_exp.config["parameters"],
            my_exp.config["n_cpus"])

        if my_exp.config["aggregation"]:
            groupscores = groups.aggregate(my_exp.exp_data["test_x_index"],
                                           result_y, my_exp.config["fake_today"])
        else:
            groupscores = []

        if my_exp.config["pilot"]:
            log.info("Generating pilot")
            pilot_y, pilot_importances, __, pilot_individual_imps = models.run(
                my_exp.pilot_data["train_x"], my_exp.pilot_data["train_y"],
                my_exp.pilot_data["test_x"], my_exp.config["model"],
                my_exp.config["parameters"], my_exp.config["n_cpus"])
            pilot_save = {"test_predictions": pilot_y,
                          "feature_importances": pilot_importances,
                          "individual_importances": pilot_individual_imps,
                          "features": my_exp.pilot_data["names"],
                          "officer_id_train": my_exp.pilot_data["train_x_index"],
                          "officer_id_test": my_exp.pilot_data["test_x_index"],
                          "train_x": my_exp.pilot_data["train_x"],
                          "train_y": my_exp.pilot_data["train_y"],
                          "test_x": my_exp.pilot_data["test_x"]}
            pilot_file = "{}pilot_experiment_{}.pkl".format(my_exp.config["pilot_dir"], timestamp)
            pickle_results(pilot_file, pilot_save)
        #commented out for now, but we need to create a flag for whether an eis system already exists in the department 
        #if config['eis_table']:
        #    confusion_matrices = scoring.test_thresholds(
        #	    my_exp.exp_data["test_x_index"], result_y, 
        #        my_exp.config['fake_today'], my_exp.exp_data["test_end_date"])
        #else:
        confusion_matrices = []
        to_save = {"test_labels": my_exp.exp_data["test_y"],
                   "test_predictions": result_y,
                   "config": my_exp.config,
                   "officer_id_train": my_exp.exp_data["train_x_index"],
                   "officer_id_test": my_exp.exp_data["test_x_index"],
                   "features": my_exp.exp_data["names"],
                   "timestamp": timestamp,
                   "parameters": my_exp.config["parameters"],
                   "train_start_date": my_exp.exp_data["train_start_date"],
                   "test_end_date": my_exp.exp_data["test_end_date"],
                   "feature_importances": importances,
                   "feature_importances_names": my_exp.exp_data["features"],
                   "aggregation": groupscores,
                   "eis_baseline": confusion_matrices,
                   "modelobj": modelobj,
                   "individual_importances": individual_imps}

        pkl_file = "{}{}_{}.pkl".format(
                    my_exp.config['directory'], my_exp.config['pkl_prefix'], timestamp)
        pickle_results(pkl_file, to_save)

        auc = scoring.compute_AUC(my_exp.exp_data["test_y"], result_y)
        dataset.enter_into_db(timestamp, my_exp.config, auc)

        if my_exp.config["auditing"]:
            audit_outputs = {"train_x": my_exp.exp_data["train_x"],
                             "train_y": my_exp.exp_data["train_y"],
                             "officer_id_train": my_exp.exp_data["train_x_index"],
                             "officer_id_test": my_exp.exp_data["test_x_index"],
                             "test_predictions": result_y,
                             "test_y": my_exp.exp_data["test_y"],
                             "test_x": my_exp.exp_data["test_x"]}
            audit_file = "{}audit_{}.pkl".format(my_exp.config['audits'], timestamp)
            pickle_results(audit_file, audit_outputs)

    log.info("Done!")
    return None


def pickle_results(pkl_file, to_save):
    """
    Save contents of experiment to pickle file for later use
    """

    with open(pkl_file, 'wb') as f:
        pickle.dump(to_save, f, protocol=pickle.HIGHEST_PROTOCOL)

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=str, help="pass your config", default="default.yaml")
    parser.add_argument( "-f", "--buildfeatures", help="build the features and stop", action='store_true' )
    args = parser.parse_args()
    main(args.config, args)
