from table import DatabaseManager, MinIOClient, initialize_app


class InfrastructureManager:
    _initialized = False

    @classmethod
    async def initialize(cls):
        if not cls._initialized:
            await initialize_app()
            _ = MinIOClient.get_client()
            cls._initialized = True
            # print("Infrastructure initialized")

    @classmethod
    async def shutdown(cls):
        if cls._initialized:
            await DatabaseManager.close()
            cls._initialized = False
            # print("Infrastructure shutdown")


initialize_infrastructure = InfrastructureManager.initialize
shutdown_infrastructure = InfrastructureManager.shutdown
