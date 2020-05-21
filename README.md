# DLGIS -- Data Library GIS dataset support

## Installation

* Install conda with python 3.8.2 and gdal 3.0.x

* Install Postgres with postgis

* Install this package: pip install git+ssh://git@bitbucket.org/iridl/dlgis.git@master


## Importing GIS datasets to Data Library

```
$ ./dlgis_import --help
Usage: dlgis_import [OPTIONS] SHAPE

  Reads SHAPE files and produces SHAPE.sql, SHAPE.tex and SHAPE.log.
  SHAPE.sql contains sql commands to create or re-create (if `--overwrite`
  is on) the table specified with `--table`. If `--table` is not specified,
  the table name is assumed to be the same as the shape name. The table
  contains artificial primary key `gid`, SHAPE attributes, original shape
  geometry `the_geom`, simplified (using tolerance factor `--tolerance`)
  shape geometry `coarse_geom`, and `label` columns. SHAPE.tex contains
  Ingrid code for corresponding Data Catalog Entry. If `--dbname` is
  provided, SHAPE.sql will be applied to the database. Currently only ESRI
  SHP format is supported (see `--format`). The SHAPE projection and
  character encoding are determined automatically. If the program fails to
  determine these parameters correctly, they can be overriden by `--srid`
  and `--encoding`.

  SHAPE - Path to input shape file

  Example: dlgis_import -d iridb -w -D "Zambia Admin Level 2 (humdata.org)"
  -l "adm0_en||'/'||adm1_en||'/'||adm2_en" shapes/zmb_admbnda_adm2_2020

Options:
  -n, --table TEXT        Table name [default: SHAPE's name]
  -G, --grid_column TEXT  Grid column  [default: gid]
  -l, --label TEXT        Label expression [default: --grid_column]
  -D, --descr TEXT        Dataset description
  -s, --srid TEXT         Input projection [default: shape's projection]
  -e, --encoding TEXT     Input encoding [default: shape's encoding]
  -O, --overwrite         Overwrite table and/or output files if exist --
                          DANGER!!!

  -t, --tolerance FLOAT   Degree of shape simplification, e.g. 0.001, 0.01,...
  -o, --output_dir PATH   Output directory [default: SHAPE's directory]
  -d, --dbname TEXT       Database name (if specified, attempts to apply SQL)
  -h, --host TEXT         Database host  [default: localhost]
  -p, --port TEXT         Database host  [default: 5432]
  -U, --username TEXT     Database user  [default: postgres]
  -W, --password          Prompt for database password
  -w, --no-password       Do not prompt for database password
  -v, --verbose           Verbose output
  --version               Show the version and exit.
  --help                  Show this message and exit.
```

## Exporting GIS datasets from Data Library

```
$ ./dlgis_export --help
Usage: dlgis_export [OPTIONS] SHAPE

  Exports a set of shapes from a Postgres table in Data Library format into
  SHAPE files.

  SHAPE - Path to output shape files

  Example: dlgis_export -d iridb -w shapes/zmb_admbnda_adm2_2020

Options:
  -q, --query TEXT        Table name or query or DL url [default: SHAPE's
                          name]

  -O, --overwrite         Overwrite output files if exist -- DANGER!!!
  -c, --coarse            Export coarse (simplified) version of the shape
  -g, --geom_column TEXT  Geometry column (overrides --coarse)
  -Z, --dont-zip          Do not zip shape files
  -o, --output_dir PATH   Output directory [default: SHAPE's directory]
  -d, --dbname TEXT       Database name  [default: iridb]
  -h, --host TEXT         Database host  [default: localhost]
  -p, --port TEXT         Database host  [default: 5432]
  -U, --username TEXT     Database user  [default: ingrid]
  -W, --password          Prompt for database password
  -w, --no-password       Do not prompt for database password
  -v, --verbose           Verbose output
  --version               Show the version and exit.
  --help                  Show this message and exit.
```
