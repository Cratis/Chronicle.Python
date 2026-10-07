# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Authenticate to a local Chronicle development kernel, register an event type and append one event.

Run ``python Samples/append_event/main.py [connection-string]``. The default connection string targets a development
kernel on localhost:35000 with the built-in development credentials.
"""

import asyncio
import sys
import uuid

from cratis_chronicle import ChronicleClient, EventTypeDefinition

DEFAULT_CONNECTION_STRING = "chronicle://localhost:35000"

BOOK_ADDED = EventTypeDefinition(
    id="python-sample.book-added",
    schema={
        "type": "object",
        "properties": {"title": {"type": "string"}, "isbn": {"type": "string"}},
        "required": ["title", "isbn"],
    },
)


async def main(connection_string: str) -> None:
    async with await ChronicleClient.connect(connection_string) as client:
        event_store = await client.ensure_event_store("python-sample")
        namespace = await event_store.ensure_namespace("Default")
        await event_store.register_event_type(BOOK_ADDED)

        result = await namespace.event_log.append(
            event_source_id=str(uuid.uuid4()),
            event_type=BOOK_ADDED,
            content={"title": "Event Sourcing in Python", "isbn": "978-0-00-000000-0"},
        )
        print(f"Appended event with sequence number {result.sequence_number}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONNECTION_STRING))
