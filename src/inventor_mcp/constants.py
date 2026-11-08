"""Inventor API enum values used by this server.

Values are taken from the Inventor type library (Inventor.ObjectTypeEnum etc.)
so the server works with late-bound COM dispatch and needs no makepy step.
"""

# DocumentTypeEnum
DOC_PART = 12290
DOC_ASSEMBLY = 12291
DOC_DRAWING = 12292
DOC_PRESENTATION = 12293

DOC_TYPES = {
    "part": DOC_PART,
    "assembly": DOC_ASSEMBLY,
    "drawing": DOC_DRAWING,
    "presentation": DOC_PRESENTATION,
}
DOC_TYPE_NAMES = {v: k for k, v in DOC_TYPES.items()}

# PartFeatureOperationEnum
OPERATIONS = {
    "join": 20481,
    "cut": 20482,
    "intersect": 20483,
    "new_body": 20485,
}

# PartFeatureExtentDirectionEnum
DIRECTIONS = {
    "positive": 20993,
    "negative": 20994,
    "symmetric": 20995,
}

# Origin work planes of a part, by index in ComponentDefinition.WorkPlanes
ORIGIN_PLANES = {"YZ": 1, "XZ": 2, "XY": 3}

# Well-known property set names
PROPSET_SUMMARY = "Inventor Summary Information"
PROPSET_DOC_SUMMARY = "Inventor Document Summary Information"
PROPSET_DESIGN = "Design Tracking Properties"
PROPSET_CUSTOM = "Inventor User Defined Properties"
