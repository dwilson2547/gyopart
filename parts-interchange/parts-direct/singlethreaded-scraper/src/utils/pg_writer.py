from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from config import Config
from utils.pg_schema import (
    car_parts_table, car_table, category_table, diagram_parts_table,
    diagram_table, engine_table, image_table, make_table, manufacturer_table,
    model_table, part_images_table, part_table, subcategory_table,
    trim_table, year_table,
)


def get_or_create_manufacturer(conn: Connection, name: str, base_url: str | None = None) -> int:
    stmt = (
        pg_insert(manufacturer_table)
        .values(name=name, base_url=base_url)
        .on_conflict_do_update(index_elements=["name"], set_={"base_url": base_url})
        .returning(manufacturer_table.c.id)
    )
    return conn.execute(stmt).scalar_one()


def get_or_create_year(conn: Connection, name: str) -> int:
    stmt = (
        pg_insert(year_table)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(year_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(year_table.c.id).where(year_table.c.name == name)).scalar_one()


def get_or_create_make(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(make_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(make_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(make_table.c.id).where(make_table.c.name == name)).scalar_one()


def get_or_create_model(conn: Connection, name: str, make_id: int, select_value: str | None = None) -> int:
    existing = conn.execute(
        select(model_table.c.id).where(
            model_table.c.name == name,
            model_table.c.make_id == make_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        model_table.insert().values(name=name, make_id=make_id, select_value=select_value)
        .returning(model_table.c.id)
    ).scalar_one()


def get_or_create_trim(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(trim_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(trim_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(trim_table.c.id).where(trim_table.c.name == name)).scalar_one()


def get_or_create_engine_row(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(engine_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(engine_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(engine_table.c.id).where(engine_table.c.name == name)).scalar_one()


def get_or_create_car(
    conn: Connection,
    year_id: int, make_id: int, model_id: int, trim_id: int, engine_id: int,
    manufacturer_id: int, base_url: str,
    car_id_str: str | None = None, vehicle_id_str: str | None = None,
) -> int:
    existing = conn.execute(
        select(car_table.c.id).where(car_table.c.base_url == base_url)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        car_table.insert().values(
            year_id=year_id, make_id=make_id, model_id=model_id,
            trim_id=trim_id, engine_id=engine_id, manufacturer_id=manufacturer_id,
            base_url=base_url, car_id=car_id_str, vehicle_id=vehicle_id_str,
        ).returning(car_table.c.id)
    ).scalar_one()


def get_or_create_category(conn: Connection, name: str) -> int:
    stmt = (
        pg_insert(category_table)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(category_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(category_table.c.id).where(category_table.c.name == name)).scalar_one()


def get_or_create_subcategory(conn: Connection, name: str, category_id: int) -> int:
    existing = conn.execute(
        select(subcategory_table.c.id).where(
            subcategory_table.c.name == name,
            subcategory_table.c.category_id == category_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        subcategory_table.insert().values(name=name, category_id=category_id)
        .returning(subcategory_table.c.id)
    ).scalar_one()


def get_or_create_part(
    conn: Connection,
    part_number: str, url: str, manufacturer_id: int,
    title: str | None = None, category_id: int | None = None,
    description: str | None = None, msrp: float | None = None,
) -> int:
    existing = conn.execute(
        select(part_table.c.id).where(part_table.c.part_number == part_number)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        part_table.insert().values(
            part_number=part_number, url=url, manufacturer_id=manufacturer_id,
            title=title, category_id=category_id, description=description, msrp=msrp,
        ).returning(part_table.c.id)
    ).scalar_one()


def get_or_create_image(
    conn: Connection,
    name: str, url: str, manufacturer_id: int,
    alt_text: str | None = None, saved: bool = False, uploaded: bool = False,
    imgcache_hash: str | None = None, imgcache_bucket: str | None = None,
) -> int:
    existing = conn.execute(
        select(image_table.c.id).where(image_table.c.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        image_table.insert().values(
            name=name, url=url, manufacturer_id=manufacturer_id,
            alt_text=alt_text, saved=saved, uploaded=uploaded,
            imgcache_hash=imgcache_hash, imgcache_bucket=imgcache_bucket,
        ).returning(image_table.c.id)
    ).scalar_one()


def mark_image_uploaded(conn: Connection, image_id: int) -> None:
    conn.execute(
        image_table.update()
        .where(image_table.c.id == image_id)
        .values(saved=True, uploaded=True)
    )


def get_or_create_diagram(
    conn: Connection,
    base_car_url: str, category_url: str,
    image_id: int | None, category_id: int, sub_category_id: int,
) -> int:
    existing = conn.execute(
        select(diagram_table.c.id).where(
            diagram_table.c.base_car_url == base_car_url,
            diagram_table.c.category_url == category_url,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        diagram_table.insert().values(
            base_car_url=base_car_url, category_url=category_url,
            image_id=image_id, category_id=category_id, sub_category_id=sub_category_id,
        ).returning(diagram_table.c.id)
    ).scalar_one()


def link_car_part(conn: Connection, car_id: int, part_id: int) -> None:
    conn.execute(
        pg_insert(car_parts_table)
        .values(car_id=car_id, part_id=part_id)
        .on_conflict_do_nothing()
    )


def link_diagram_part(conn: Connection, diagram_id: int, part_id: int, part_index: str | None = None) -> None:
    conn.execute(
        pg_insert(diagram_parts_table)
        .values(diagram_id=diagram_id, part_id=part_id, part_index=part_index)
        .on_conflict_do_nothing()
    )


def link_part_image(conn: Connection, part_id: int, image_id: int, text: str | None = None) -> None:
    conn.execute(
        pg_insert(part_images_table)
        .values(part_id=part_id, image_id=image_id, part_image_text=text)
        .on_conflict_do_nothing()
    )


def _parse_category_from_url(url: str) -> tuple[str, str]:
    """Extract (category_name, subcategory_name) from a diagram page URL.

    URL pattern: /v-{year}-{make}-{model}--{trim}--{engine}/{category}/{subcategory}
    Car slugs start with 'v-'; domain/scheme segments are skipped.
    """
    from urllib.parse import urlparse
    path = urlparse(url).path if url else ""
    segments = [s for s in path.split("/") if s and not s.startswith("v-")]
    if len(segments) >= 2:
        raw_cat = segments[-2].replace("-", " ").title()
        raw_sub = segments[-1].replace("-", " ").title()
    elif len(segments) == 1:
        raw_cat = segments[0].replace("-", " ").title()
        raw_sub = raw_cat
    else:
        raw_cat, raw_sub = "Unknown", "Unknown"
    return raw_cat, raw_sub


def write_car_data(
    engine: Engine,
    car_context: dict,
    diagrams_data: list,
    parts_data: dict,
    manufacturer_id: int,
    imgcache_hashes: dict | None = None,
) -> None:
    """Write all structured data for one engine config to parts_interchange.

    car_context keys: year, make_url, make_name, model_url, model_name,
                      trim_url, trim_name, engine_url, engine_name, base_url
    diagrams_data: list of parsed_diagrams dicts from process_car_data
    parts_data: {part_number: part_data dict}
    imgcache_hashes: {image_url: content_hash} from _cache_image calls
    """
    hashes = imgcache_hashes or {}
    with engine.begin() as conn:
        year_id = get_or_create_year(conn, str(car_context["year"]))
        make_id = get_or_create_make(conn, car_context["make_name"], car_context["make_url"])
        model_id = get_or_create_model(conn, car_context["model_name"], make_id, car_context["model_url"])
        trim_id = get_or_create_trim(conn, car_context["trim_name"], car_context["trim_url"])
        eng_id = get_or_create_engine_row(conn, car_context["engine_name"], car_context["engine_url"])
        car_id = get_or_create_car(
            conn, year_id, make_id, model_id, trim_id, eng_id,
            manufacturer_id, car_context["base_url"],
        )

        for diagram_page in diagrams_data:
            if diagram_page.get("skipped"):
                continue
            for diagram in diagram_page.get("diagrams", []):
                if diagram.get("skipped"):
                    continue
                category_url = diagram.get("category_link", "")
                cat_name, sub_cat_name = _parse_category_from_url(category_url)
                category_id = get_or_create_category(conn, cat_name)
                sub_category_id = get_or_create_subcategory(conn, sub_cat_name, category_id)

                img_id: int | None = None
                img_name = diagram.get("img", "")
                if img_name:
                    img_url = diagram.get("img_url", "")
                    full_img_url = "https:" + img_url if img_url.startswith("//") else img_url
                    img_id = get_or_create_image(
                        conn, img_name, full_img_url, manufacturer_id,
                        alt_text=diagram.get("alt_text"),
                        imgcache_hash=hashes.get(full_img_url),
                        imgcache_bucket=Config.IMG_BUCKET if hashes.get(full_img_url) else None,
                    )

                diagram_id = get_or_create_diagram(
                    conn, diagram.get("base_car_url", ""), category_url,
                    img_id, category_id, sub_category_id,
                )

                for ref_code, part_numbers in diagram.get("parts", {}).items():
                    for pn in part_numbers:
                        pdata = parts_data.get(pn)
                        if not pdata or pdata.get("skipped"):
                            continue
                        part_url = pdata.get("url", "")
                        part_id = get_or_create_part(
                            conn,
                            part_number=pn,
                            url=part_url,
                            manufacturer_id=manufacturer_id,
                            title=pdata.get("title"),
                            category_id=category_id,
                            description=str(pdata.get("details", {})) if pdata.get("details") else None,
                            msrp=pdata.get("msrp"),
                        )
                        link_car_part(conn, car_id, part_id)
                        link_diagram_part(conn, diagram_id, part_id, ref_code)

                        for img_rec in pdata.get("images", []):
                            for slot in ("main", "preview", "thumb"):
                                slot_data = img_rec.get(slot)
                                if not slot_data:
                                    continue
                                raw_img_url = slot_data.get("url", "")
                                full_url = "https:" + raw_img_url if raw_img_url.startswith("//") else raw_img_url
                                fname = full_url.split("/")[-1]
                                if not fname:
                                    continue
                                pi_id = get_or_create_image(
                                    conn, fname, full_url, manufacturer_id,
                                    alt_text=slot_data.get("alt_text"),
                                    imgcache_hash=hashes.get(full_url),
                                    imgcache_bucket=Config.IMG_BUCKET if hashes.get(full_url) else None,
                                )
                                link_part_image(conn, part_id, pi_id, slot)
