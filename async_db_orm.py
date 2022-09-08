# -*- coding: utf-8 -*-
from peewee import *
import config

db_path = config.PRODUCTION_DB
if config.TEST_MODE:
    db_path = config.TEST_DB
db = SqliteDatabase(db_path)

class RaceCategory(Model):
    id = IntegerField(primary_key=True)
    name = CharField()
    description = CharField()

    class Meta:
        table_name = 'race_categories'
        database = db

class AsyncRace(Model):
    id = IntegerField(primary_key= True)
    start = DateField()
    seed = CharField()
    description = CharField()
    additional_instructions = CharField()
    category_id = IntegerField()
    active = BooleanField(default=False)

    class Meta:
        table_name = 'async_races'
        database = db

class AsyncRacer(Model):
    user_id = IntegerField(primary_key=True)
    username = CharField()
    wheel_weight = IntegerField()

    class Meta:
        table_name = 'async_racers'
        database = db

class AsyncSubmission(Model):
    id = IntegerField(primary_key=True)
    submit_date = DateTimeField()
    race_id = IntegerField()
    user_id = IntegerField()
    username = CharField()
    finish_time_rta = CharField()
    finish_time_igt = CharField()
    collection_rate = IntegerField()
    next_mode = CharField(null=True)
    comment = CharField(null=True)

    class Meta:
        table_name = 'async_submissions'
        database = db

class RaceRoster(Model):
    id = IntegerField(primary_key=True)
    race_id = IntegerField()
    user_id = IntegerField()

    class Meta:
        table_name = 'async_race_rosters'
        database = db

####################################################################################################################
# Checks the database for the required tables, creating them if they don't exist.
def check_add_db_tables():
    logging.info("Checking DB tables")
    tables = db.get_tables()

    if 'race_categories' not in tables:
        RaceCategory.create_table()

    if 'async_races' not in tables:
        AsyncRace.create_table()

    if 'async_racers' not in tables:
        AsyncRacer.create_table()

    if 'async_submissions' not in tables:
        AsyncSubmission.create_table()

    if 'async_race_rosters' not in tables:
        RaceRoster.create_table()
