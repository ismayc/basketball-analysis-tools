1e-13  # reconciliation magnitude; verified live by 03_reconcile's gate
2,000  # the rotation outcome's minutes threshold (2,000+ NBA minutes within three seasons), a setting
14 @ (the outcome) |  # API calls, one per season 2011-12 to 2024-25 (data/nba_min holds 14 files), a harvest fact
1 @ at pick  # the pick at which the curve's edge value is read, a position on the axis, not a result
