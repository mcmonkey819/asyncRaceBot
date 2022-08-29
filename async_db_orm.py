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
