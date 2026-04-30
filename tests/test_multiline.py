# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vools.datetime import EnhancedDateFormatter


def test_multiline_expression():
    """测试花括号内多行表达式支持"""
    # Test 1: Multiline expression inside curly braces
    template1 = """Result: {
        name <- "Zhang San"
        ; age <- 30
        ; city <- "Beijing"
        ; name + " is " + str(age) + " years old"
    }"""
    
    formatter1 = EnhancedDateFormatter(template1)
    result1 = formatter1.format()
    assert "Zhang San is 30 years old" in result1

    # Test 2: Multiline list comprehension
    template2 = """List: {
        age <- 30
        ; ",".join([
            str(i)
            for i in range(age)
            if i % 5 == 0
        ])
    }"""
    
    formatter2 = EnhancedDateFormatter(template2)
    result2 = formatter2.format()
    assert "0,5,10,15,20,25" in result2

    # Test 3: Complex multiline expression
    template3 = """Complex calc: {
        x <- 10
        ; y <- 20
        ; z <- 30
        ; (x + y) * z
    }"""
    
    formatter3 = EnhancedDateFormatter(template3)
    result3 = formatter3.format()
    assert "900" in result3

    # Test 4: Multiline text with multiline expression
    template4 = """Name: {name}
Age: {age}
Calculation: {
    a <- 100
    ; b <- 200
    ; a + b
}"""
    
    formatter4 = EnhancedDateFormatter(template4)
    formatter4.set(name="Li Si", age=25)
    result4 = formatter4.format()
    assert "Li Si" in result4
    assert "25" in result4
    assert "300" in result4

    print("All multiline expression tests passed!")


def test_guide_examples():
    """测试 USER_GUIDE.md 中的示例代码"""
    # 基本用法测试
    formatter1 = EnhancedDateFormatter("今天是 {run_date_std}，本周开始于 {run_week_begin_std}")
    result1 = formatter1.format()
    assert "今天是" in result1
    assert "本周开始于" in result1

    # 上下文变量动态更新
    template2 = "{name <- \"张三\" ; age <- 30 ; city <- \"北京\" ; name + \"今年\" + str(age) + \"岁，来自\" + city}"
    formatter2 = EnhancedDateFormatter(template2)
    result2 = formatter2.format()
    assert "张三今年30岁，来自北京" in result2

    # SQL 模板应用
    sql_template = """
SELECT 
    user_id,
    user_name,
    register_time,
    total_amount
FROM users
WHERE 
    register_time >= '{start_date}'
    AND register_time < '{end_date}'
    AND status = {status}
    AND age BETWEEN {min_age} AND {max_age}
ORDER BY register_time DESC
LIMIT {limit};
"""
    formatter3 = EnhancedDateFormatter(sql_template)
    formatter3.set(
        start_date="2026-01-01",
        end_date="2026-05-01",
        status=1,
        min_age=18,
        max_age=60,
        limit=100
    )
    sql = formatter3.format()
    assert "SELECT" in sql
    assert "FROM users" in sql
    assert "WHERE" in sql

    # 高级 SQL 模板（带动态计算）
    sql_template2 = """
-- 查询日期：{run_date_std}
-- 查询范围：{days_ago <- 7 ; days_ago} 天前至 {run_date_std}

SELECT 
    DATE_FORMAT(order_time, '%Y-%m-%d') AS date,
    COUNT(*) AS order_count
FROM orders
WHERE 
    order_time >= DATE_SUB('{run_date_std}', INTERVAL {days_ago} DAY)
GROUP BY DATE_FORMAT(order_time, '%Y-%m-%d');
"""
    formatter4 = EnhancedDateFormatter(sql_template2)
    formatter4.set(days_ago=31) # days_ago = 31 被覆盖 ，使用模板中的 days_ago = 7，模板中的变量赋值优先级高
    sql2 = formatter4.format()
    assert "-- 查询日期" in sql2
    assert "FROM orders" in sql2
    assert "INTERVAL 7 DAY" in sql2  # 验证使用的是 7，而不是 31
    
    # 测试变量赋值优先级
    template_priority = "{days_ago <- 7 ; days_ago}"
    formatter_priority = EnhancedDateFormatter(template_priority)
    formatter_priority.set(days_ago=31)
    result_priority = formatter_priority.format()
    assert result_priority == "7"  # 模板中的 7 覆盖了 set 设置的 31
    
    print("All USER_GUIDE.md examples tests passed!")



def test_sql_template():
    """测试 run_date_end 变量"""
    template5 = r"""
    {
        gap <- 10;
        tbi <- "user_if_drawdown_tb";
        dt <- get_week(run_date_std,gap)
    }
    select 
        user_id,
        user_name,
        register_time,
        total_amount
    from {tbi}
    where dt >= '{dt}'
    """
    from vools.datetime import get_week,vicDate
    run_date_std = vicDate().run_date_standard
    gap = 10
    print(get_week(run_date_std,gap))
    formatter5 = EnhancedDateFormatter(template5,get_week = get_week)
    s = formatter5.format()
    print(s)
    print("All run_date_end tests passed!")



if __name__ == "__main__":
    test_multiline_expression()
    test_guide_examples()
    test_sql_template()