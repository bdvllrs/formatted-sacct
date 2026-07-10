# squeue and sacct displayed with rich

Use:
```
uvx rs --from https://github.com/bdvllrs/formatted-sacct.git
```
Or install
```
uv tool install rs --from https://github.com/bdvllrs/formatted-sacct.git
```

## Commands

Display my jobs (equivalent to `sacct -u $USER`)
```
rs me
```

Display job info (equivalent to `sacct -j <job_id>`):
```
rs job <job_id>
```

Display queue (equivalent to `squeue`):
```
rs queue
```

Display my jobs in queue (equivalent to `squeue --me`):
```
rs queue --me
```

All these command can take additional sacct arguments.

Display available columns:

```
rs columns
```

Change the displayed columns:

```
rs --columns "Job Id:job_id,Mem:tres.mem" ...
```

# Environment variables
```
RS_COLUMNS="Job Id:job_id,Mem:tres.mem"
```
To change the displayed columns.

```
RS_COLOR_ERROR="red"
RS_COLOR_RUNNING="green"
RS_COLOR_PENDING="blue"
```

To change the displayed colors.


