import shutil
import os

path = os.path.join(os.path.dirname(__file__), "templates", "admin")
if os.path.exists(path):
    shutil.rmtree(path)
    print("Deleted templates/admin successfully")
else:
    print("templates/admin does not exist")
