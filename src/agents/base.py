class BaseAgent:

    name = None
    description = None

    def __init__(self):
        pass

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement this method.")
    
    @property
    def intents(self) -> list[str]:
        raise NotImplementedError("Subclasses must implement this property.")