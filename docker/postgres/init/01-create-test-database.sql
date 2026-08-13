-- Runs only on first initialisation of the postgres volume.
-- `make db-test-up` creates this database on existing volumes.
CREATE DATABASE fpl_test OWNER fpl;
