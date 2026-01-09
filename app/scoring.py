def points(pred_home: int, pred_away: int, act_home: int | None, act_away: int | None) -> int | None:
    if act_home is None or act_away is None:
        return None
    if pred_home == act_home and pred_away == act_away:
        return 5

    pred_diff = pred_home - pred_away
    act_diff = act_home - act_away

    if (pred_diff > 0 and act_diff > 0) or (pred_diff < 0 and act_diff < 0) or (pred_diff == 0 and act_diff == 0):
        return 1
    return 0
