#
# Copyright (c) 2020 IRI, Columbia University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is furnished to do so, subject
# to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
from typing import Dict, Tuple, List, Optional, Union, Final
import sys
import io
import os
import traceback
import pathlib
import zipfile
import subprocess
from glob import iglob
from datetime import datetime
from datetime import timezone
import click
import shapefile
from osgeo import osr
from dlgis.__about__ import version


SRID_TO: Final[str] = "4326"
PRIMARY_KEY_COLUMN: Final[str] = "gid"
GEOM_COLUMN: Final[str] = "the_geom"
COARSE_GEOM_COLUMN: Final[str] = "coarse_geom"


def logg(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def run_shell(cmd: str) -> None:
    # logg(f"run_shell: {cmd!r}")
    subprocess.check_call(cmd, shell=True)


def escape_squote_shell(s: Union[str, pathlib.Path]) -> str:
    return str(s).replace("'", "'\"'\"'")


def escape_dquote_pgsql(s: str) -> str:
    return s.replace('"', '""')


def parentheses_check(s: str) -> str:
    counter = 0
    for c in s:
        if c == "(":
            counter += 1
        elif c == ")":
            if counter != 0:
                counter -= 1
            else:
                raise Exception(f"Unbalanced ')' in {s!r}")
    if counter != 0:
        raise Exception(f"Unbalanced {'(' * counter!r} in {s!r}")
    return s


def esriprj2standards(
    shapeprj_path: pathlib.Path, encoding: str
) -> Dict[str, Optional[str]]:
    with open(shapeprj_path, "r", encoding=encoding) as f:
        prj_txt = f.read()
    srs = osr.SpatialReference()
    srs.ImportFromESRI([prj_txt])
    srs.AutoIdentifyEPSG()
    return dict(
        prj=prj_txt,
        wkt=srs.ExportToWkt(),
        proj4=srs.ExportToProj4(),
        epsg=srs.GetAuthorityCode(None),
    )


@click.command()
@click.argument("shape", type=pathlib.Path)
@click.option("-n", "--table", help="Table name [default: SHAPE's name]")
@click.option(
    "-f",
    "--format",
    default="shp",
    type=click.Choice(["shp"], case_sensitive=False),
    help="Shape format",
    show_default=True,
)
@click.option(
    "-G", "--grid_column", default="gid", help="Grid column", show_default=True
)
@click.option("-l", "--label", help="Label expression [default: --grid_column]")
@click.option("-D", "--descr", help="Dataset description")
@click.option("-s", "--srid", help="Input projection [default: shape's projection]")
@click.option("-e", "--encoding", help="Input encoding [default: shape's encoding]")
@click.option(
    "-O",
    "--overwrite",
    "overwrite_flag",
    is_flag=True,
    help="Overwrite table and/or output files if exist -- DANGER!!!",
)
@click.option(
    "-t",
    "--tolerance",
    help="Degree of shape simplification, e.g. 0.001, 0.01,...",
    show_default=True,
    type=float,
)
@click.option(
    "-o",
    "--output_dir",
    type=pathlib.Path,
    help="Output directory [default: SHAPE's directory]",
)
@click.option(
    "-d", "--dbname", help="Database name (if specified, attempts to apply SQL)"
)
@click.option(
    "-h", "--host", default="localhost", help="Database host", show_default=True
)
@click.option("-p", "--port", default="5432", help="Database host", show_default=True)
@click.option(
    "-U", "--username", default="postgres", help="Database user", show_default=True
)
@click.option(
    "-W",
    "--password",
    "prompt_password",
    flag_value=True,
    default=True,
    type=click.BOOL,
    help="Prompt for database password",
)
@click.option(
    "-w",
    "--no-password",
    "prompt_password",
    flag_value=False,
    type=click.BOOL,
    help="Do not prompt for database password",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.version_option(version, "--version", show_default=False)
@click.help_option("--help", show_default=False)
def import_shapes(
    shape: pathlib.Path,
    table: Optional[str],
    format: str,
    grid_column: str,
    label: Optional[str],
    descr: Optional[str],
    srid: Optional[str],
    encoding: Optional[str],
    overwrite_flag: bool,
    tolerance: Optional[float],
    output_dir: Optional[pathlib.Path],
    host: str,
    port: int,
    dbname: Optional[str],
    username: str,
    prompt_password: bool,
    verbose: bool,
) -> int:
    """ Reads SHAPE files and produces SHAPE.sql, SHAPE.tex and SHAPE.log.
        SHAPE.sql contains sql commands to create or re-create (if `--overwrite` is on)
        the table specified with `--table`. If `--table` is not specified, the table
        name is assumed to be the same as the shape name. The table contains artificial
        primary key `gid`, SHAPE attributes, original shape geometry `the_geom`,
        simplified (using tolerance factor `--tolerance`) shape geometry `coarse_geom`,
        and `label` columns. SHAPE.tex contains Ingrid code for corresponding Data
        Catalog Entry. If `--dbname` is provided, SHAPE.sql will be applied to the
        database. Currently only ESRI SHP format is supported (see `--format`). The
        SHAPE projection and character encoding are determined automatically. If the
        program fails to determine these parameters correctly, they can be overriden by 
        `--srid` and `--encoding`. 

        \b
        SHAPE - Path to input shape file
        
        Example: dlgis_import -d iridb -w -D "Zambia Admin Level 2 (humdata.org)"
        -l "adm0_en||'/'||adm1_en||'/'||adm2_en" shapes/zmb_admbnda_adm2_2020
        \f
    """
    shape_log: Optional[pathlib.Path] = None
    try:
        if format not in ("shp"):
            raise Exception(f"Shape format {format!r} is not supported.")

        password = os.environ.get("PGPASSWORD")
        if password is None and dbname is not None and prompt_password:
            password = click.prompt("Password", hide_input=True)

        if table is None:
            table = shape.stem

        # shp2pgsql does not support table names with quotes
        if "'" in table or '"' in table:
            raise Exception(f"Table name {table!r} must not contain quotes.")

        shape_shp: Final[pathlib.Path] = shape.with_suffix(".shp")
        shape_prj: Final[pathlib.Path] = shape.with_suffix(".prj")

        if output_dir is None:
            output_dir = shape.parent

        output_path: Final[pathlib.Path] = output_dir / shape.stem

        shape_log = output_path.with_suffix(".log")
        shape_sql: Final[pathlib.Path] = output_path.with_suffix(".sql")
        shape_tex: Final[pathlib.Path] = output_path.with_suffix(".tex")

        if not overwrite_flag:
            for suffix in (".tex", ".sql", ".log"):
                if output_path.with_suffix(suffix).exists():
                    raise Exception(
                        f"File {str(output_path.with_suffix(suffix))!r} "
                        f"exists. Use --overwrite to overwrite it."
                    )

        version_and_time_stamp: Final[str] = (
            f"Generated by dlgis_import version {version} on "
            f"{datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}"
        )

        logg(
            f"dlgis_import: importing {str(shape)!r} into "
            f"{table!r}{'@'+dbname if dbname is not None else ''}, "
            f"SQL={str(shape_sql)!r}, TEX={str(shape_tex)!r}, "
            f"LOG={str(shape_log)!r}"
        )

        with open(shape_log, "w") as f:
            f.write(f"{version_and_time_stamp}\n\n")

        with shapefile.Reader(str(shape)) as sf:
            if encoding is not None:
                encoding_from = encoding
            else:
                encoding_from = sf.encoding

            if encoding_from is None:
                raise Exception("Could not obtain encoding.")

            if srid is not None:
                srid_from = srid
            else:
                srid_optional = esriprj2standards(shape_prj, encoding_from)["epsg"]
                if srid_optional is not None:
                    srid_from = srid_optional
                else:
                    raise Exception("Could not obtain srid.")

            fields: List[Tuple[str, str, int, int]] = [
                (a.lower(), b, c, d)
                for a, b, c, d in sf.fields
                if a.lower() != "deletionflag"
            ]

            if grid_column not in [a for a, _, _, _ in fields] + [PRIMARY_KEY_COLUMN]:
                raise Exception(
                    f"Grid column attribute does not exist, "
                    f"choose from {[a for a, _, _, _ in fields]!r}"
                )

            if label is None:
                label = grid_column

            index_content = f"""\
{version_and_time_stamp}

Table: {table!r}
No. of shapes: {len(sf)}
Shape type: {sf.shapeTypeName!r} /{sf.shapeType!r}
Original encoding: {encoding_from!r}
Original projection: {srid_from!r}
Bbox: {sf.bbox!r}
Mbox: {sf.mbox!r}
Zbox: {sf.zbox!r}
Fields: {fields!r}

\\begin{{ingrid}}
continuedataset:

/name ({parentheses_check(table)}) cvn def
"""
            if descr is not None:
                index_content += f"""\
/description ({parentheses_check(descr)}) def
"""
            index_content += "\n"

            for c_name, c_type, c_len, _ in fields:
                index_content += f"""\
({parentheses_check(c_name)}) cvn {{IRIDB ({parentheses_check(table)}) \
({parentheses_check(c_name)}) [ ({parentheses_check(grid_column)}) ]
    open_column_by /long_name ({parentheses_check(c_name)}) def }}defasvarsilentnoreuse
"""

            index_content += f"""\

/the_geom {{IRIDB ({parentheses_check(table)}) \
({GEOM_COLUMN if tolerance is None else COARSE_GEOM_COLUMN}) \
[ ({parentheses_check(grid_column)}) ]
    open_column_by /long_name ({GEOM_COLUMN}) def }}defasvarsilentnoreuse

/label {{IRIDB ({parentheses_check(table)}) \
({parentheses_check(label)} as label) [ ({parentheses_check(grid_column)}) ]
    open_column_by /long_name (label) def }}defasvarsilentnoreuse

:dataset

label ({parentheses_check(grid_column)}) cvn cvx exec exch pop name exch def
\\end{{ingrid}}
"""

        with open(shape_tex, "w") as f:
            f.write(index_content)

        with open(shape_sql, "w") as f:
            f.write(
                f"""\
-- {version_and_time_stamp}

\\set ON_ERROR_STOP ON

"""
            )
            if overwrite_flag:
                f.write(
                    f"""\
DROP TABLE IF EXISTS "{escape_dquote_pgsql(table)}";

"""
                )

        run_shell(
            f"shp2pgsql -s '{escape_squote_shell(srid_from)}:{SRID_TO}' "
            f"-W '{escape_squote_shell(encoding_from)}' "
            f"-c -I -e -g '{GEOM_COLUMN}' "
            f"'{escape_squote_shell(shape_shp)}' '{escape_squote_shell(table)}' "
            f">> '{escape_squote_shell(shape_sql)}' "
            f"2>> '{escape_squote_shell(shape_log)}'"
        )

        if tolerance is not None:
            run_shell(
                f"grep AddGeometryColumn '{escape_squote_shell(shape_sql)}' | "
                f"sed '1,$s/{GEOM_COLUMN}/{COARSE_GEOM_COLUMN}/' "
                f">> '{escape_squote_shell(shape_sql)}' "
                f"2>> '{escape_squote_shell(shape_log)}'"
            )

            with open(shape_sql, "a") as f:
                f.write(
                    f"""\
UPDATE "{escape_dquote_pgsql(table)}" set {COARSE_GEOM_COLUMN} =
    ST_Multi(ST_SimplifyPreserveTopology({GEOM_COLUMN},{tolerance}));
CREATE INDEX ON "{escape_dquote_pgsql(table)}" USING GIST ({COARSE_GEOM_COLUMN});
ANALYZE "{escape_dquote_pgsql(table)}";
GRANT SELECT ON "{escape_dquote_pgsql(table)}" TO PUBLIC;

SELECT {PRIMARY_KEY_COLUMN}, ST_NPoints({GEOM_COLUMN}) as original_length,
    ST_NPoints({COARSE_GEOM_COLUMN}) as simplified_length,
    ST_NPoints({COARSE_GEOM_COLUMN})::real / ST_NPoints({GEOM_COLUMN})
    FROM "{escape_dquote_pgsql(table)}"
    ORDER BY {PRIMARY_KEY_COLUMN};
"""
                )

        if dbname is not None:
            if password is not None:
                os.environ["PGPASSWORD"] = password

            run_shell(
                f"psql -1 -a -h '{escape_squote_shell(host)}' -p {port} "
                f"-d '{escape_squote_shell(dbname)}' "
                f"-U '{escape_squote_shell(username)}' "
                f"< '{escape_squote_shell(shape_sql)}' "
                f">> '{escape_squote_shell(shape_log)}' 2>&1"
            )

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        with io.StringIO() as f:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, limit=10, file=f
            )
            logg(f"dlgis_import error: {e if not verbose else f.getvalue()}")
            if shape_log is not None:
                logg(f"Also see {str(shape_log)!r}.")
        return 1

    return 0


@click.command()
@click.argument("shape", type=pathlib.Path)
@click.option(
    "-q",
    "--query",
    "table_or_query",
    help="Table name or query [default: SHAPE's name]",
)
@click.option(
    "-f",
    "--format",
    default="shp",
    type=click.Choice(["shp"], case_sensitive=False),
    help="Output shape format",
    show_default=True,
)
@click.option(
    "-s",
    "--srid",
    default="4326",
    help="Output projection",
    show_default=True,
    hidden=True,
)
@click.option(
    "-e",
    "--encoding",
    default="utf-8",
    help="Output encoding",
    show_default=True,
    hidden=True,
)
@click.option(
    "-O",
    "--overwrite",
    "overwrite_flag",
    is_flag=True,
    help="Overwrite output files if exist -- DANGER!!!",
)
@click.option(
    "-c",
    "--coarse",
    "coarse_flag",
    is_flag=True,
    help="Export coarse (simplified) version of the shape",
)
@click.option("-g", "--geom_column", help="Geometry column (overrides --coarse)")
@click.option(
    "-Z", "--dont-zip", "dont_zip_flag", is_flag=True, help="Do not zip shape files"
)
@click.option(
    "-o",
    "--output_dir",
    type=pathlib.Path,
    help="Output directory [default: SHAPE's directory]",
)
@click.option(
    "-d", "--dbname", default="iridb", help="Database name", show_default=True
)
@click.option(
    "-h", "--host", default="localhost", help="Database host", show_default=True
)
@click.option("-p", "--port", default="5432", help="Database host", show_default=True)
@click.option(
    "-U", "--username", default="ingrid", help="Database user", show_default=True
)
@click.option(
    "-W",
    "--password",
    "prompt_password",
    flag_value=True,
    default=True,
    type=click.BOOL,
    help="Prompt for database password",
)
@click.option(
    "-w",
    "--no-password",
    "prompt_password",
    flag_value=False,
    type=click.BOOL,
    help="Do not prompt for database password",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.version_option(version, "--version", show_default=False)
@click.help_option("--help", show_default=False)
def export_shapes(
    shape: pathlib.Path,
    table_or_query: Optional[str],
    format: str,
    srid: str,
    encoding: str,
    overwrite_flag: bool,
    coarse_flag: bool,
    geom_column: Optional[str],
    dont_zip_flag: bool,
    output_dir: Optional[pathlib.Path],
    host: str,
    port: int,
    dbname: str,
    username: str,
    prompt_password: bool,
    verbose: bool,
) -> int:
    """ Exports a set of shapes from a Postgres table in Data Library format into
        SHAPE files. 

        \b
        SHAPE - Path to output shape files
        
        Example: dlgis_export -d iridb -w shapes/zmb_admbnda_adm2_2020
        \f
    """
    shape_log: Optional[pathlib.Path] = None
    try:
        if format not in ("shp"):
            raise Exception(f"Shape format {format!r} is not supported.")

        password = os.environ.get("PGPASSWORD")
        if password is None and prompt_password:
            password = click.prompt("Password", hide_input=True)

        if table_or_query is None:
            table_or_query = shape.stem

        if geom_column is None:
            geom_column = COARSE_GEOM_COLUMN if coarse_flag else GEOM_COLUMN

        if output_dir is None:
            output_dir = shape.parent

        output_path: Final[pathlib.Path] = output_dir / shape.stem

        if not overwrite_flag:
            for suffix in (".zip", ".shp", ".dbf", ".prj", ".log"):
                if output_path.with_suffix(suffix).exists():
                    raise Exception(
                        f"File {str(output_path.with_suffix(suffix))!r} "
                        f"exists. Use --overwrite to overwrite it."
                    )

        shape_log = output_path.with_suffix(".log")

        version_and_time_stamp: Final[str] = (
            f"Generated by dlgis_export version {version} on "
            f"{datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}"
        )

        logg(
            f"dlgis_export: exporting {table_or_query!r}@{dbname!r} to {str(output_path)!r}"
        )

        with open(shape_log, "w") as f:
            f.write(f"{version_and_time_stamp}\n\n")

        if password is not None:
            os.environ["PGPASSWORD"] = password

        run_shell(
            f"pgsql2shp -f '{escape_squote_shell(output_path)}' "
            f"-u '{escape_squote_shell(username)}' "
            f"-g '{escape_squote_shell(geom_column)}' "
            f"-h '{escape_squote_shell(host)}' "
            f"-p {port} '{escape_squote_shell(dbname)}' "
            f"'{escape_squote_shell(table_or_query)}' >> '{shape_log}' 2>&1"
        )

        shape_zip: Final[pathlib.Path] = output_path.with_suffix(".zip")

        if not dont_zip_flag:
            with zipfile.ZipFile(shape_zip, "w") as zf:
                for path in (
                    pathlib.Path(x) for x in iglob(str(output_path.with_suffix(".*")))
                ):
                    if path.suffix not in (".zip", ".sql", ".tex"):
                        zf.write(path, path.name)
                        path.unlink()
        elif shape_zip.exists():
            shape_zip.unlink()

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        with io.StringIO() as f:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, limit=10, file=f
            )
            logg(f"dlgis_export error: {e if not verbose else f.getvalue()}")
            if shape_log is not None:
                logg(f"Also see {str(shape_log)!r}.")
        return 1

    return 0
