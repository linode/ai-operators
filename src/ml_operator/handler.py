import kopf


@kopf.on.create("akamaiknowledgebases")
async def created(spec, **_):
    pass


@kopf.on.update("akamaiknowledgebases")
async def updated(spec, old, new, diff, **_):
    pass


@kopf.on.delete("akamaiknowledgebases")
async def deleted(spec, **_):
    pass
