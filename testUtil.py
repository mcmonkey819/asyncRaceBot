from async_db_orm import *
db = SqliteDatabase('testDbUtil.db')
db.bind([RaceCategory, AsyncRace, AsyncRacer, AsyncSubmission])

# Helpful script used to test database functions/commands in isolation.

def sort_igt(submission):
    igt = submission.finish_time_igt
    # Convert the time to seconds for sorting
    ret = 0
    if igt is not None:
        parts = igt.split(':')
        ret = (3600 * int(parts[0])) + (60 * int(parts[1])) + int(parts[2])
    return ret

def test_lambda():
    x = 100
    l = lambda y: x + y
    return l(20)