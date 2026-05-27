class TangoAddon:
    def __init__(self, graph, results):
        self.results = results
        self.graph = graph

    def post_process(self):
        """Post Process the result."""
        raise NotImplementedError("post_process method should be implemented by the add-on.")

    def execute(self):
        """Execute the add-on."""
        raise NotImplementedError("execute method should be implemented by the add-on.")
