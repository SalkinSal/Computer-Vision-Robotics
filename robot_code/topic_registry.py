from typing import Literal

from topic import Topic, TopType
from utils.print_utils import print_locked as print
from utils.config_utils import Struct

class TopicRegistry:
    """
    The TopicRegistry holds a copy of each topic, in which it initializes the shared memory
    of the ring buffer and orderly closes the same at the end of the program.

    The registry uses the Context Manager pattern to ensure an orderly release of all shared memory
    if there is an error or the framework stops unexpectedly. To accomplish this,
    the Topics are only instantiated in the enter() method, not at init().

    The registry also allows the main process to read topics (e.g. for the publisher)
    and can be updated to allow the main process to publish to topics directly (e.g. for logging).
    """
    # =====================================
    #     START & STOP
    # =====================================
    def __init__(self, topic_config:Struct):
        """
        Initialize topic registry.

        Parameters
        ----------
        topic_config:   Struct
            Parsed config containing details of each topic.
        """
        self.topic_config = topic_config
        
        self.topics = {}

    def __enter__(self):
        """
        When entering the context, instantiate the a copy of every topic.
        
        Since these are the registry copies, they are instantiated first
        and create the shared memory that all other copies of the topic use.

        Returns
        -------
        TopicRegistry
            Reference to itself.
        """
        # instantiate every topic
        for t_name, t_config in self.topic_config.topics.items():
            self.topics[t_name] = Topic(type=TopType.REG, name=t_name, config=t_config)
        return self

    def __exit__(self, exc_type, exc, tb):
        """
        Orderly release all shared memory in the registry-copies of each topic.
        
        Parameters
        ----------
        Default parameters for __exit__ method.
        """
        for t in self.topics.values():
            t.close()


    # =====================================
    #     PUB/SUB
    # =====================================
    def read_message_from_topic(self, t_name:str, max_msgs:int=0, new_only:bool=True) -> list:
        """
        Read messages using the registry copy of a specific topic.

        Either get only new messages if there are any, up to a maximum number
        or get a set number of messages, whether they are new or not.
        In either case, all messages in the topic are marked as read/not new.

        This method allows functions in the main process (e.g. the Publisher)
        to access messages published to topics.

        Parameters
        ----------
        t_name:     str
                    Name of the topic.
        max_msgs:   int
                    How many messages to retrieve (starting with the newest). 0 gets all new messages if there are any.
        new_only:   bool
                    Whether to get only new messages or the max number of messages whether already read or not.
                    If new_only is False, max_msgs must not be 0!

        Returns
        -------
        list or None
            List containing one or more messages or None if messages could not be retrieved or there were no new messages.
        """
        return self.topics[t_name].get_msg(max_msgs, new_only)

    def synced_message_from_topic(
            self,
            t_name:str,
            timestamp:int,
            max_distance:int,
            field_name:str="timestamp",
            direction:Literal["newer", "older", "nearest"]="nearest",
            ) -> tuple:
            """
            Find closest message to the timestamp using the registry copy of a specific topic.
    
            This method allows functions in the main process (e.g. the Publisher)
            to access messages published to topics.
    
            Parameters
            ----------
            t_name:     str
                        Name of the topic.
            timestamp : float
                The timestamp to sync messages to.
            max_distance: int
                Maximum distance between timestamp and message in seconds.
            field_name: str
                Name of the message field to sync to. default="timestamp".
            direction : {"older", "newer", "nearest"}, default="nearest"
                Search direction:
                - "older": Closest message at or before the timestamp.
                - "newer": Closest message at or after the timestamp.
                - "nearest": Closest message overall.
    
            Returns
            -------
            tuple or None
                Message closest to timestamp within given parameters or None if no such message was found.
            """
            return self.topics[t_name].get_synced_msg(timestamp,max_distance,field_name,direction)


    # =====================================
    #     AUXILIARY METHODS
    # =====================================
    def has_topic(self, t_name:str) -> bool:
        """
        Check whether a topic exists.

        Parameters
        ----------
        t_name:   str
                Name of the topic in question.

        Returns
        -------
        bool
            True if topic exists, else False
        """
        return t_name in self.topics

    def get_topic_config(self, t_name:str) -> Struct:
        """
        Get the config of one specific topic.

        Parameters
        ----------
        t_name:   str
                Name of the topic in question.

        Returns
        -------
        Struct or dict
            Config of the topic in question.
        """
        return self.topics[t_name].get_config()

    def __str__(self):
        return f"TopicRegistry (Topics: {[t for t in self.topics.keys()]})"

    def __repr__(self):
        return f"TopicRegistry (Topics: {[t for t in self.topics.keys()]})"