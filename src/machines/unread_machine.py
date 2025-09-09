from loguru import logger

from .base_machine import BaseMachine


class UnreadMachine(BaseMachine):
    """
    stateDiagram-v2
    [*] --> idle: reset
    [*] --> idle: fallback [unhandled]

    idle --> wait_mark_as_read: get_unread_history [is_unread_history]

    wait_mark_as_read --> idle: mark_as_read [yes && is_mark_as_read]
    wait_mark_as_read --> idle: finalize [no]
    """

    def __init__(self):
        # Define states
        states = [
            'idle',
            'wait_mark_as_read'
        ]

        # Define transitions
        transitions = [
            # Initial transitions to idle
            {
                'trigger': 'reset',
                'source': '*',
                'dest': 'idle',
                'before': 'before_reset',
                'after': 'after_reset'
            },
            {
                'trigger': 'fallback',
                'source': '*',
                'dest': 'idle',
                'conditions': ['is_unhandled'],
                'before': 'before_fallback',
                'after': 'after_fallback'
            },
            
            # From idle to wait_mark_as_read
            {
                'trigger': 'get_unread_history',
                'source': 'idle',
                'dest': 'wait_mark_as_read',
                'conditions': ['is_unread_history'],
                'before': 'before_get_unread_history',
                'after': 'after_get_unread_history'
            },
            
            # From wait_mark_as_read back to idle
            {
                'trigger': 'mark_as_read',
                'source': 'wait_mark_as_read',
                'dest': 'idle',
                'conditions': ['is_yes', 'is_mark_as_read'],
                'before': 'before_mark_as_read',
                'after': 'after_mark_as_read'
            },
            {
                'trigger': 'finalize',
                'source': 'wait_mark_as_read',
                'dest': 'idle',
                'conditions': ['is_no'],
                'before': 'before_finalize',
                'after': 'after_finalize'
            }
        ]

        # Initialize the machine
        super().__init__(
            states=states,
            transitions=transitions,
            initial='idle'
        )

    # Condition methods
    def is_unhandled(self):
        """Check if the event is unhandled"""
        logger.debug("Checking if event is unhandled")
        # TODO: Implement condition logic
        return True

    def is_unread_history(self):
        """Check if there is unread history"""
        logger.debug("Checking if there is unread history")
        # TODO: Implement condition logic
        return True

    def is_yes(self):
        """Check if the answer is yes"""
        logger.debug("Checking if answer is yes")
        # TODO: Implement condition logic
        return True

    def is_mark_as_read(self):
        """Check if mark as read is requested"""
        logger.debug("Checking if mark as read is requested")
        # TODO: Implement condition logic
        return True

    def is_no(self):
        """Check if the answer is no"""
        logger.debug("Checking if answer is no")
        # TODO: Implement condition logic
        return True

    # Before callback stubs
    def before_reset(self):
        """Called before reset transition"""
        logger.info("Before reset transition")
        # TODO: Implement before reset logic

    def before_fallback(self):
        """Called before fallback transition"""
        logger.info("Before fallback transition")
        # TODO: Implement before fallback logic

    def before_get_unread_history(self):
        """Called before get_unread_history transition"""
        logger.info("Before get_unread_history transition")
        # TODO: Implement before get_unread_history logic

    def before_mark_as_read(self):
        """Called before mark_as_read transition"""
        logger.info("Before mark_as_read transition")
        # TODO: Implement before mark_as_read logic

    def before_finalize(self):
        """Called before finalize transition"""
        logger.info("Before finalize transition")
        # TODO: Implement before finalize logic

    # After callback stubs
    def after_reset(self):
        """Called after reset transition"""
        logger.info("After reset transition - now in idle state")
        # TODO: Implement after reset logic

    def after_fallback(self):
        """Called after fallback transition"""
        logger.info("After fallback transition - now in idle state")
        # TODO: Implement after fallback logic

    def after_get_unread_history(self):
        """Called after get_unread_history transition"""
        logger.info("After get_unread_history transition - now in wait_mark_as_read state")
        # TODO: Implement after get_unread_history logic

    def after_mark_as_read(self):
        """Called after mark_as_read transition"""
        logger.info("After mark_as_read transition - now in idle state")
        # TODO: Implement after mark_as_read logic

    def after_finalize(self):
        """Called after finalize transition"""
        logger.info("After finalize transition - now in idle state")
        # TODO: Implement after finalize logic