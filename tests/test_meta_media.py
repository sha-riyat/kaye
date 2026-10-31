from app.meta_media import count_boxes

SAM_TEXT = (
    "<0f>0<|box;x1=997;y1=886;x2=1417;y2=1148;w=1600;h=1600;c=0.90|><|mask;x=0;y=0;data=1,1,!!|>,"
    "1<|box;x1=565;y1=666;x2=1077;y2=961;w=1600;h=1600;c=0.91|><|mask;x=0;y=0;data=1,1,!!|>,"
    "2<|box;x1=0;y1=1155;x2=20;y2=1416;w=1600;h=1600;c=0.57|><|mask;x=0;y=0;data=1,1,!!|>"
)


def test_count_keeps_confident_boxes_only():
    assert count_boxes(SAM_TEXT) == 2  # the 0.57 sliver at the image edge is not a sack


def test_count_without_confidence_counts_every_box():
    assert count_boxes("0<|box;x1=1;y1=1;x2=2;y2=2;w=9;h=9|>,1<|box;x1=3;y1=3;x2=4;y2=4;w=9;h=9|>") == 2


def test_no_match_is_zero():
    assert count_boxes("") == 0
