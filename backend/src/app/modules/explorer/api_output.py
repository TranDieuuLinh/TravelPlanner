from app.modules.explorer.adapters.auto_tags import YamlPlaceTagCatalog
from app.modules.explorer.contract import ExplorerApiOutput, ExplorerOutput
from app.modules.explorer.ports import PlaceTagCatalog


def to_explorer_api_output(
    output: ExplorerOutput,
    *,
    tag_catalog: PlaceTagCatalog | None = None,
) -> ExplorerApiOutput:
    catalog = tag_catalog or YamlPlaceTagCatalog()
    return ExplorerApiOutput.from_internal(output, tags_for=catalog.tags_for)
