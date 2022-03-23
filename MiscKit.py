import datetime, sys, traceback, json
from threading import Lock

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
        locks[file_name] = Lock()
    
    locks[file_name].acquire()

    try:
        with open(file_name) as json_file:
            data = json.load(json_file)

            for key, value in data.items():
                data_dict[key] = value

    except FileNotFoundError:
        locks[file_name].release()
        save(file_name, data_dict)
        load(file_name, data_dict)

    locks[file_name].release()


# save json file
def save(file_name, data_dict):

    global locks

    if file_name not in locks:
        locks[file_name] = Lock()

    locks[file_name].acquire()

    with open("data_list.json", "w") as json_file:
        json.dump(data_dict, json_file, indent=4)

    locks[file_name].release()
