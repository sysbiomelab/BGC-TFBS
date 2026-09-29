# BGC-TFBS

Code for the BGC-TFBS website.

**Website:** https://bgc-tfbs.sites.er.kcl.ac.uk/

**Run:**

```bash
pip install -r webapp/requirements.txt
uvicorn --app-dir webapp app.main:app
```

Set `WEBSITE_DB` to point to the database.

**Data:** The database and underlying files are available on Zenodo:
[10.5281/zenodo.22766286](https://doi.org/10.5281/zenodo.22766286)

**Author:** Idris Matine, QSys Lab, Centre for Host-Microbiome Interactions, King's College London.

**Cite:** Paper to be added.

**Licence:** Code MIT (see [LICENSE](LICENSE)); data CC BY 4.0.
