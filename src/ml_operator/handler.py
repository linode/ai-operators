from .resource import AkamaiKnowledgeBase


class Handler:
    async def created(self, namespace: str, name: str, kb: AkamaiKnowledgeBase):
        pass

    async def updated(self, namespace: str, name: str, kb: AkamaiKnowledgeBase):
        pass

    async def deleted(self, namespace: str, name: str, kb: AkamaiKnowledgeBase):
        pass
