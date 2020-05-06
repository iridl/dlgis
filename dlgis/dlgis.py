from typing import (Dict, Optional)
import sys
import io
import os
import traceback
import pathlib
from datetime import datetime
from datetime import timezone
import click
import shapefile
from osgeo import osr
from dlgis.__about__ import version


def logg(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def run_cmd(cmd: str, raise_excpt: bool = True) -> int:
    # logg(f"run_cmd: {cmd!r}")
    ret = os.system(cmd) >> 8
    if ret != 0 and raise_excpt:
        raise Exception(f"Command {cmd!r} returned {ret}.")
    return ret


def escq(s: str, qs: str = "'", es: str = "'") -> str:
    return s.replace(qs, es)


def esriprj2standards(shapeprj_path: pathlib.Path, encoding: str) -> Dict[str, str]:
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
    help="Shape format [supported formats: shp]",
    show_default=True,
)
@click.option(
    "-l", "--label", default="gid", help="Label expression", show_default=True
)
@click.option("-D", "--descr", help="Dataset description")
@click.option("-s", "--srid", help="Input projection [default: shape's projection]")
@click.option("-e", "--encoding", help="Input encoding [default: shape's encoding]")
@click.option(
    "-O",
    "--overwrite",
    "drop_flag",
    is_flag=True,
    help="Drop table if exists. DANGER!!!",
)
@click.option(
    "-t",
    "--tolerance",
    help="Degree of shape simplification, e.g. 0.0001, 0.001, 0.01, etc.",
    show_default=True,
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
)
@click.option(
    "-w", "--no-password", "prompt_password", flag_value=False, type=click.BOOL
)
@click.version_option(version, "--version", show_default=False)
@click.help_option("--help", show_default=False)
def import_shapes(
    shape: pathlib.Path,
    table: str,
    format: str,
    label: str,
    descr: Optional[str],
    srid: Optional[str],
    encoding: Optional[str],
    drop_flag: bool,
    tolerance: Optional[float],
    output_dir: Optional[pathlib.Path],
    host: str,
    port: int,
    dbname: Optional[str],
    username: str,
    prompt_password: bool,
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
    try:
        if format not in ("shp"):
            raise Exception(f"Shape format {format!r} is not supported.")

        password = os.environ.get("PGPASSWORD")
        if password is None and dbname is not None and prompt_password:
            password = click.prompt("Password", hide_input=True)

        if table is None:
            table = shape.stem

        srid_to = "4326"
        primary_key_column = "gid"
        geom_column = "the_geom"
        coarse_geom_column = "coarse_geom"
        
        shape_shp = shape.with_suffix(".shp")
        shape_prj = shape.with_suffix(".prj")

        if output_dir is None:
            output_dir = shape.parent

        output_path = output_dir / table

        shape_log = output_path.with_suffix(".log")
        shape_sql = output_path.with_suffix(".sql")
        shape_tex = output_path.with_suffix(".tex")

        version_and_time_stamp = (
            f"Generated by dlgis_import version {version} on "
            f"{datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}"
        )

        logg(
            f"Importing {str(shape)!r} into TABLE={table!r}, "
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
                srid_from = esriprj2standards(shape_prj, encoding_from)["epsg"]

            if srid_from is None:
                raise Exception("Could not obtain srid.")

            fields = [
                (a.lower(), b, c, d)
                for a, b, c, d in sf.fields
                if a.lower() != "deletionflag"
            ]

            index_content = f"""\
{version_and_time_stamp}

Table: {table}
No. of shapes: {len(sf)}
Shape type: {sf.shapeTypeName} ({sf.shapeType})
Original encoding: {encoding_from}
Original projection: {srid_from}
Bbox: {sf.bbox}
Mbox: {sf.mbox}
Zbox: {sf.zbox}
Fields: {fields}

\\begin{{ingrid}}
continuedataset:

/name ({table}) cvn def
"""
            if descr is not None:
                index_content += f"""\
/description ({descr}) def
"""
            index_content += "\n"

            for c_name, c_type, c_len, _ in fields:
                index_content += f"""\
({c_name}) cvn {{IRIDB ({table}) ({c_name}) [ ({primary_key_column}) ]
    open_column_by /long_name ({c_name}) def }}defasvarsilentnoreuse
"""

            index_content += f"""\

/the_geom {{IRIDB ({table}) ({geom_column if tolerance is None else coarse_geom_column}) [ ({primary_key_column}) ]
    open_column_by /long_name ({geom_column}) def }}defasvarsilentnoreuse

/label {{IRIDB ({table}) ({label} as label) [ ({primary_key_column}) ]
    open_column_by /long_name (label) def }}defasvarsilentnoreuse

:dataset
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

        shp2pgsql_mode = "-d" if drop_flag else "-c"
        run_cmd(
            f"shp2pgsql -s '{escq(srid_from)}:{escq(srid_to)}' -W '{escq(encoding_from)}' "
            f"{shp2pgsql_mode} -I -e -g '{geom_column}' '{shape_shp}' "
            f"'{escq(table)}' >> '{shape_sql}' 2>> '{shape_log}'"
        )

        if tolerance is not None:
            run_cmd(
                f"grep AddGeometryColumn '{shape_sql}' | "
                f"sed '1,$s/{geom_column}/{coarse_geom_column}/' "
                f">> '{shape_sql}' 2>> '{shape_log}'"
            )

            with open(shape_sql, "a") as f:
                f.write(
                    f"""\
UPDATE "{escq(table, qs='"', es='""')}" set {coarse_geom_column} =
    ST_Multi(ST_SimplifyPreserveTopology({geom_column},{tolerance}));
CREATE INDEX ON "{escq(table, qs='"', es='""')}" USING GIST ("{coarse_geom_column}");
ANALYZE "{escq(table, qs='"', es='""')}";
GRANT SELECT ON "{escq(table, qs='"', es='""')}" TO PUBLIC;

SELECT {primary_key_column}, ST_NPoints({geom_column}) as original_length,
    ST_NPoints({coarse_geom_column}) as simplified_length,
    ST_NPoints({coarse_geom_column})::real / ST_NPoints({geom_column})
    FROM "{escq(table, qs='"', es='""')}"
    ORDER BY {primary_key_column};
"""
                )

        if dbname is not None:
            if password is not None:
                os.environ["PGPASSWORD"] = password

            run_cmd(
                f"psql -1 -h '{escq(host)}' -p {port} -d '{escq(dbname)}' "
                f"-U '{escq(username)}' < {shape_sql} >> '{shape_log}' 2>&1"
            )

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        with io.StringIO() as f:
            traceback.print_exception(
                exc_type, exc_value, exc_traceback, limit=5, file=f
            )
            logg(f"Error: {e}\nAlso see {str(shape_log)!r}.")
            logg(f"Error: {f.getvalue()}\nAlso see {str(shape_log)!r}.")
        return 1

    return 0
