# Samples

A sample uses the local client package, contains no credentials beyond the documented local-development defaults, and
is run against a development kernel before it is presented as working.

## append_event

[`append_event/main.py`](append_event/main.py) authenticates to a local development kernel, ensures an event store and
the `Default` namespace, registers an event type with a JSON schema and appends one event.

```shell
docker run -d --name chronicle-python-sample -p 127.0.0.1:35000:35000 cratis/chronicle:16.38.2-development
python Samples/append_event/main.py                          # chronicle://localhost:35000
python Samples/append_event/main.py chronicle://localhost:19300   # another port
docker rm -f chronicle-python-sample
```

It prints `Appended event with sequence number <n>`.
