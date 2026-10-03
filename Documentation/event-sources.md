---
title: Event source and stream definitions
description: Define registered event sources and streams and resolve append routing and concurrency (partial parity).
---

`cratis_chronicle.event_sources` provides the transport-independent part of registered event source parity
(Chronicle 19.30.0, Cratis/Chronicle#4516): definitions, validation, and append routing/concurrency resolution.
Routing belongs to the append, not to event types.

```python
from cratis_chronicle.event_sources import (
    ConcurrencyDimensions, EventSourceDefinition, EventStreamDefinition, resolve_routing,
)

account = EventSourceDefinition(
    "Account",
    concurrency=ConcurrencyDimensions.EVENT_SOURCE_ID,
    streams=(EventStreamDefinition("Transactions", concurrency=ConcurrencyDimensions.EVENT_SOURCE_ID | ConcurrencyDimensions.EVENT_STREAM_ID),),
)
routing = resolve_routing({account.name: account}, "Account", "Transactions")
```

Rules: names must be non-empty and unique; unknown sources/streams raise; an explicit concurrency scope always wins,
then the stream default, then the source default; a per-event source override does not inherit a call-level stream;
no source means the source stays unset.

## Not yet available

Wire registration (`EventSources` service), definition-aware append, and `EventContext`/observer metadata are blocked:
the published `cratis-chronicle-contracts` wheel (16.38.2) has no `eventsources` module, Chronicle 19.30.0 publishes no
Python contracts (the publish job is held off upstream), and this client has no connection/append API yet (issue #4).
