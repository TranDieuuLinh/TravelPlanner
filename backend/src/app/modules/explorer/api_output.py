from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.contract import ExplorerApiOutput, ExplorerOutput
from app.modules.explorer.ports import TagCatalog


def to_explorer_api_output(
    output: ExplorerOutput,
    *,
    tag_catalog: TagCatalog | None = None,
) -> ExplorerApiOutput:
    catalog = tag_catalog or YamlTagCatalog()
    return ExplorerApiOutput.from_internal(output, filter_tags=catalog.filter_allowed)
