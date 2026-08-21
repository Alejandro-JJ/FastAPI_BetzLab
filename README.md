## BetzLab FastAPI project - Analysis tools

- FastAPI -> frontend
- Redis -> message broker
- Celery -> background worker
- Python -> heavy computation

# Progress
- First draft works with a simple task, celery is listening to redis running in a docker container
- Upload of pic, tranformation to B&W, re-saving
- Connection with database working with posts /register and /login
- Dummy functions can be replaced with proper analysis functions (Segmentation, SHDecomposition, TractionForceMicroscopy...) once architecture works
- Architecture structured in a docker compose [DB, redis, backend, worker, frontend]
- Started a draft of frontend, with basic login page


