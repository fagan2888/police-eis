DROP TABLE IF EXISTS staging.lookup_training_types; 
CREATE UNLOGGED TABLE staging.lookup_training_types (
	code                                                                  int,                --
	value                                                                 varchar,            --
	description                                                           varchar             --
);
