from dagster import DailyPartitionsDefinition, MonthlyPartitionsDefinition

# Dùng chung partition để tránh import vòng giữa assets
covid_partitions = DailyPartitionsDefinition(
    start_date="2020-01-01",
    timezone="Asia/Ho_Chi_Minh",
)

covid_monthly_partitions = MonthlyPartitionsDefinition(
    start_date="2020-01-01",
    timezone="Asia/Ho_Chi_Minh",
)
