import datetime, sys, traceback, json
from time import sleep

locks = {}


# logger for errors
def log_error(*args):

    print("\n", datetime.datetime.now())

    for i in args:
        print(i)

    print(traceback.print_exception(*sys.exc_info()))


# logger for messages
def log_message(*args):

    print("\n", datetime.datetime.now())

    for i in args:
        print(i)


# load json file
def load(file_name, data_dict):

    global locks

    if file_name not in locks:
        locks[file_name] = False

    while locks[file_name]:
        log_message("Loading file %s" % (file_name), "locked")
        sleep(1)
    
    locks[file_name] = True

    try:
        with open(file_name) as json_file:
            data = json.load(json_file)

            for key, value in data.items():
                data_dict[key] = value

    except FileNotFoundError:
        locks[file_name] = False
        save(file_name, data_dict)
        load(file_name, data_dict)

    locks[file_name] = False


# save json file
def save(file_name, data_dict):

    global locks

    if file_name not in locks:
        locks[file_name] = False

    while locks[file_name]:
        log_message("Saving file %s" % (file_name), "locked")
        sleep(1)
    
    locks[file_name] = True

    with open("data_list.json", "w") as json_file:
        json.dump(data_dict, json_file)

    locks[file_name] = False
