"""Extract inline Lambda source (Code.ZipFile) from the CloudFormation template.

All Lambda code in this project lives inline in
infrastructure/cmw-infra.yml as `Code.ZipFile` blocks, so unit tests
have to pull the source back out of the YAML. CloudFormation uses custom tags
(!Sub, !Ref, !GetAtt, ...) that stock PyYAML rejects; register a permissive
multi-constructor so the document parses and we can reach the ZipFile strings.
"""
import os
import yaml

TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "infrastructure", "cmw-infra.yml",
)


class _CfnLoader(yaml.SafeLoader):
    pass


def _passthrough(loader, tag_suffix, node):
    # We only care about ZipFile strings, not intrinsic values. Collapse every
    # CloudFormation tag to a harmless placeholder so the document loads.
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _passthrough)


def load_template(path=TEMPLATE):
    with open(path) as fh:
        return yaml.load(fh, Loader=_CfnLoader)


def lambda_sources(path=TEMPLATE):
    """Return {logical_id: python_source} for every inline Lambda function."""
    template = load_template(path)
    out = {}
    for logical_id, res in (template.get("Resources") or {}).items():
        if res.get("Type") != "AWS::Lambda::Function":
            continue
        code = (res.get("Properties") or {}).get("Code") or {}
        # Packaged functions set Code to a local-path string; only inline
        # functions carry a ZipFile. Guard the type so the former is skipped.
        if isinstance(code, dict) and "ZipFile" in code:
            out[logical_id] = code["ZipFile"]
    return out


if __name__ == "__main__":
    for name, src in lambda_sources().items():
        print(f"# ==== {name} ({len(src.splitlines())} lines) ====")
