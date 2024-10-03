# extra conf folder

Put in any extra configuration for apps. Example:

```
zep/
  config.yaml
```

And then reference those from `db.yaml` like this:

```yaml
volumes:
  - ../../conf/zep/zep.yaml:/app/zep.yaml
```
