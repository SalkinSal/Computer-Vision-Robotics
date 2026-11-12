'''
This package runs a suite of checks and substitutions on the config objects.
Current functions:
    PARSE MAIN
        - Add print lock to the main config so all nodes can use it to avoid BlockingIoExceptions.
    
    PARSE NODES
        - Check that each node listed in `included` has a config.
        - Delete configs for ndoes that are not included.
        - Add parameters to all node configs that will be set by the node registry (is_dummy, dummy_queues).
          
    Parse TOPICS
        - Update topic configs
            - Check that message formats are valid (func. from message_utils.)
            - Add publisher and subscriber attributes to the configs.
            - Replace generic buffer lengths in topic config with numerical values.
            - Instantiate read/write locks for each topic config.  
            - Where a msg field is a n-dimensional list, turn the dtype format from a list (needed by yaml) into a tuple (needed by numpy).
        - Get publishers from node config and add them to the topic config.
            - Make sure each topic has at most one publisher.
            - Give a warning for each topic without a publisher.
        - Get subscribers from node config and add them to topic config.
        - delete any topics that have neither publisher nor subscribers

    IMPLEMENTATION-SPECIFIC FUNCTIONS:
        - correctly format camera matrix & distortion coefficients in main config
        - replace image dimension placeholders in relevant topic configs with values from the main config
    

'''

import numpy as np
from multiprocessing import Lock

try:
    from utils.print_utils import print_locked as print
    from utils.message_utils import check_msg_fmt
except:
    from rich import print
    from message_utils import check_msg_fmt
    print("[yellow][bold]Modified imports in config_parser!")


# =====================================
#     MAIN PARSER
# =====================================
def parse_configs(configs):
    """
    Parse the provided configs. For a list of functions currently in use, see the top of the file.

    If you add any parsing functions, remember to call them from this method!

    Parameters
    ----------
    configs: Struct
        Struct (dict-like) containing the configs included for the framework.
        Currently: main, node, topic. The individual config objects are edited in place.
    Returns
    -------
    Struct
        The parsed configs.
    """
    main_config = configs.mc
    node_config = configs.nc
    topic_config = configs.tc

    # PARSE MAIN
    # ---------------------------------
    parse_main(mc=main_config)
    
    # PARSE NODES
    # verify inlcuded nodes
    if not clean_nodes(nc=node_config):
        return None
    update_nodes(nc=node_config)

    # PARSE TOPICS
    # ---------------------------------
    # check message dtypes, add pub and sub attributes, replace buffer lengths, 
    # instantiate locks, and convert nd dtype formats
    if not update_topic_configs(tc=topic_config):
        return None
    
    # verify topic publishers
    if not check_pubs(nodes=node_config.nodes, tc=topic_config):
        return None

    # verify topic subscribers
    if not check_subs(nodes=node_config.nodes, tc=topic_config):
        return None

    # remove unused topics
    find_orphan_topics(tc=topic_config)


    # IMPLEMENTATION-SPECIFIC
    # ---------------------------------
    # calculate camera matrix & distrortion coefficients and add them to main config
    update_camera(mc=main_config)
    # replace placeholders for image dimensions
    update_img(mc=main_config, tc=topic_config)

    return configs


# =====================================
#     PARSE MAIN
# =====================================
def parse_main(mc):
    """
    Instantiate print_lock in main config.
    
    Parameters
    ----------
    mc: Struct
        Main config.
    """
    mc.print_lock = Lock()


# =====================================
#     PARSE NODES
# =====================================
def clean_nodes(nc) -> bool:
    """
    Check whether each node listed in `included` has a config and delete
    the configs of any node that was not included.

    If an included node doesn't have a config defined, it is given a dummy config:
    - `class_name = None`
    - `queues= []`
    - `topics= {"pubs": [], "subs": []}`

    Parameters
    ----------
    nc: Struct
        Node config.
    
    Returns
    -------
    bool
        True if parsing was successful, else False.
    """
    all_nodes = list(nc.nodes.keys())
    
    # check if all nodes listed in "include" have node configs
    for n in nc.include:
        if n in all_nodes:
            all_nodes.remove(n) # rmv from list so only not-included nodes remain
        else:
            print(f"[bold][yellow]Node [blue]{n}[/blue] does not have a node config and will be run as a dummy node!")
            # add dummy config (will get turned into nested Struct)
            nc.nodes[n] = {
                "class_name": None,
                "queues": [],
                "topics": {"pubs": [], "subs":[]}
            }

    # delete the configs of any node not listed in included
    for n in all_nodes:
        del nc.nodes[n]
    return True

def update_nodes(nc):
    """
    Add those parameters to all node configs that will be set by the node registry.

    Paramters
    ---------
    nc: Struct
        Node config.
    """
    for n_config in nc.nodes.values():
        n_config.is_dummy = False
        n_config.dummy_queues = []


# =====================================
#     PARSE TOPICS
# =====================================
def update_topic_configs(tc) -> bool:
    """
    Update topic configs:
    - check format of message dtypes
    - add publisher and subscriber attributes.
    - replace generic buffer lengths with specific values.
    - convert n-dim array dtype format from list to tuple
    - instantiate read/write locks

    Paramters
    ---------
    tc: Struct
        Topic config.
    
    Returns
    -------
    bool
        True if message was formatted correctly, False if not.
    """
    # replace generic buffer lenghts with nos. from main config,
    # and instantiate a lock for each topic
    buffers = {
        "long": tc.buffer_length.long,
        "medium": tc.buffer_length.medium,
        "short": tc.buffer_length.short,
        "min": tc.buffer_length.min
    }
    for t, config in tc.topics.items():
        # check dtypes formating
        if not check_msg_fmt(t_name=t, dtypes=config.dtypes):
            return False
        # add pub/sub attributes
        config.publisher = None
        if "subscribers" not in config: # topics needed by main process already have subscriber list
            config.subscribers = []

        # replace buffer length
        config["buffer_length"] = buffers[config["buffer_length"]]
        
        # instantiate lock
        config["lock"] = Lock()

        # turn dtype lists into tuples
        dtypes = config["dtypes"]["formats"]
        for i, dt in enumerate(dtypes):
            if isinstance(dt, list):
                dt_tuple = (dt[0], tuple(dt[1]))
                dtypes[i] = dt_tuple
    return True

def check_pubs(nodes, tc) -> bool:
    """
    Get the publisher for each topic from the node config and add them to the topic config.

    Asserts that every topic has at most one publisher.

    Paramters
    ---------
    nodes:  Struct
        Dictionary of all nodes and their configs.
    tc:     Struct
        Topic config.

    Returns
    -------
    bool
        True if parsing was successful, else False.
    """
    topic_list = list(tc.topics.keys())
    for n, config in nodes.items():
        for t in config.topics.pubs:
            try:
                i = topic_list.index(t)
            except:
                print(f"[bold][red]Node [blue]{n}[/blue] cannot publish to topic [bright_blue]{t}[/bright_blue]: "
                      + "topic does not exist or already has a publisher!")
                return False

            # add the current node as publisher to the topic
            tc.topics[t].publisher = n

            # delete the topic from list to provoke error 
            # if a second node tries to register as publisher
            del topic_list[i]
    return True


def check_subs(nodes, tc) -> bool:
    """
    Get the subscribers for each topic from the node config and add them to the topic's config.

    Paramters
    ---------
    nodes:  Struct
        Dictionary of all nodes and their configs.
    tc:     Struct
        Topic config.

    Returns
    -------
    bool
        True if parsing was successful, else False.
    """
    for n, config in nodes.items():

        for t in config.topics.subs:
            # check that topic exists 
            if t not in tc.topics.keys():
                print(f"[bold][red]Node [blue]{n}[/blue] cannot subscribe to topic [bright_blue]{t}[/bright_blue] since it does not exist.")
                return False

            # add the current node to the topic's subscriber list
            tc.topics[t].subscribers.append(n)
    return True

def find_orphan_topics(tc):
    """
    Give a warning if a topic has no publisher and remove all topics that have neither publisher nor subscribers.
    
    Parameters
    ----------
    tc: Struct
        Topic config.
    """
    # list of topics to be deleted
    to_delete = []

    for t, t_config in tc.topics.items():
        # check if topic has publisher
        if t_config.publisher is not None:
            continue

        # check if topic has subscribers
        if len(t_config.subscribers) > 0:
            # keep topic but warn about missing publisher
            print(f"[bold][yellow]Topic [bright_blue]{t}[/bright_blue] has no publisher!")
        else:
            # topics has neither publisher nor subscribers
            to_delete.append(t)

    # delete all orphan topics
    for t in to_delete:
        del tc.topics[t]


# =====================================
#     IMPLEMENTATION-SPECIFIC
# =====================================
# NOTE JJ: Method adapted rom the original "Introduction to Computer Vision and Robotics" framework.
def update_camera(mc):
    """
    Reshape the camera matrix and distortion coefficients to match the dimensions given in the main config.
    
    Parameters
    ----------
    mc: Struct
        Main config.
    """
    cam_matrix = mc.camera.camera_intrinsics.camera_matrix
    mc.camera.camera_intrinsics.camera_matrix = np.array(cam_matrix.data).reshape((cam_matrix.rows, cam_matrix.cols))
    dist_c = mc.camera.camera_intrinsics.distortion_coefficients
    mc.camera.camera_intrinsics.distortion_coefficients = np.array(dist_c.data).reshape((dist_c.rows, dist_c.cols))


def update_img(mc, tc):
    """
    Replace placeholders for image height and width in relevant topics with the values from the main config.

    Add any topic names and the names of the image-message-field to the topics-dict.
    Assumes image fields have format ["im_height", "img_width", channels]

    Parameters
    ----------
    mc: Struct
        Main config.
    tc: Struc
        Topic config.
    """
    topics = {"camera_capture": "img",
              "marker_detections": "draw_img"}

    # update im_width and im_height in camera_capture
    im_height = mc.camera.im_height
    im_width = mc.camera.im_width
    for t_name, field in topics.items():
        if t_name not in tc.topics:
            continue

        # find index of the field in list of dtypes
        dtypes = tc.topics[t_name].dtypes
        idx = dtypes.names.index(field)

        # replace placeholders with values from main config
        dtype, (_, _, channels) = dtypes.formats[idx]
        new_fmt = (dtype, (im_height, im_width, channels))

        # save new format to config
        tc.topics[t_name].dtypes.formats[idx] = new_fmt    