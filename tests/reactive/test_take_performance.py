"""take 操作符性能基准测试 - 验证优化效果"""
import timeit
import gc
import vools.reactive as rx
import reactivex as rxx
from reactivex.operators import take


def benchmark_take():
    """测试不同数据量下的take性能"""
    print("=" * 80)
    print("take 操作符性能基准测试 - vools vs reactivex")
    print("=" * 80)
    
    test_configs = [
        # (数据总量, take数量, 迭代次数)
        (10000, 100, 50),    # 大数据量，取少量
        (10000, 1000, 50),   # 大数据量，取中等量
        (10000, 5000, 30),   # 大数据量，取大量
        (100, 50, 100),      # 小数据量，取一半
        (1000, 100, 80),     # 中等数据量，取少量
    ]
    
    results = []
    
    for total, take_n, iterations in test_configs:
        gc.collect()
        
        # vools测试
        vools_timer = timeit.Timer(
            stmt=f'rx.of(*range({total})).pipe(rx.take({take_n})).subscribe(on_next=lambda x: None)',
            setup='import vools.reactive as rx'
        )
        vools_times = vools_timer.repeat(repeat=5, number=iterations)
        vools_avg = sum(vools_times) / len(vools_times) / iterations * 1000000
        
        # reactivex测试
        rxx_timer = timeit.Timer(
            stmt=f'rxx.of(*range({total})).pipe(take({take_n})).subscribe(on_next=lambda x: None)',
            setup='import reactivex as rxx; from reactivex.operators import take'
        )
        rxx_times = rxx_timer.repeat(repeat=5, number=iterations)
        rxx_avg = sum(rxx_times) / len(rxx_times) / iterations * 1000000
        
        ratio = rxx_avg / vools_avg
        status = "vools更快" if ratio > 1 else "rxx更快"
        
        results.append({
            'total': total,
            'take': take_n,
            'vools': vools_avg,
            'rxx': rxx_avg,
            'ratio': ratio,
            'status': status
        })
        
        print(f"\n数据总量={total}, take={take_n}:")
        print(f"  vools: {vools_avg:.2f}µs")
        print(f"  rxx:   {rxx_avg:.2f}µs")
        print(f"  性能比: {ratio:.2f}x [{status}]")
    
    # 总结报告
    print("\n" + "=" * 80)
    print("测试总结:")
    print("=" * 80)
    print(f"{'数据总量':<10} {'take数量':<10} {'vools(µs)':<12} {'rxx(µs)':<12} {'性能比':<10} {'状态':<15}")
    print("-" * 80)
    for r in results:
        print(f"{r['total']:<10} {r['take']:<10} {r['vools']:<12.2f} {r['rxx']:<12.2f} {r['ratio']:<10.2f} {r['status']:<15}")
    
    avg_ratio = sum(r['ratio'] for r in results) / len(results)
    vools_wins = sum(1 for r in results if r['ratio'] > 1)
    rxx_wins = sum(1 for r in results if r['ratio'] < 1)
    
    print("\n总体结果:")
    print(f"  vools胜出: {vools_wins}次")
    print(f"  rxx胜出: {rxx_wins}次")
    print(f"  平均性能比: {avg_ratio:.2f}x")
    print(f"  性能提升: {(avg_ratio - 1) * 100:.1f}%")
    
    if avg_ratio > 1:
        print("\n✅ vools take操作符已超越reactivex性能!")
    elif avg_ratio < 1:
        gap = (1 - avg_ratio) * 100
        print(f"\n⚠️  性能差距: {gap:.1f}%，需要进一步优化")
    else:
        print("\n🎯 性能持平")


def benchmark_edge_cases():
    """测试边缘情况性能"""
    print("\n" + "=" * 80)
    print("边缘情况性能测试")
    print("=" * 80)
    
    # 测试1: take(0) - 空操作
    gc.collect()
    vools_empty = timeit.timeit(
        'rx.of(*range(10000)).pipe(rx.take(0)).subscribe(on_next=lambda x: None)',
        setup='import vools.reactive as rx',
        number=100
    )
    rxx_empty = timeit.timeit(
        'rxx.of(*range(10000)).pipe(take(0)).subscribe(on_next=lambda x: None)',
        setup='import reactivex as rxx; from reactivex.operators import take',
        number=100
    )
    
    print(f"\ntake(0)测试 (10000个元素，取0个):")
    print(f"  vools: {vools_empty / 100 * 1000000:.2f}µs")
    print(f"  rxx:   {rxx_empty / 100 * 1000000:.2f}µs")
    print(f"  性能比: {rxx_empty / vools_empty:.2f}x")
    
    # 测试2: take(全部) - 无提前终止
    gc.collect()
    vools_full = timeit.timeit(
        'rx.of(*range(1000)).pipe(rx.take(1000)).subscribe(on_next=lambda x: None)',
        setup='import vools.reactive as rx',
        number=50
    )
    rxx_full = timeit.timeit(
        'rxx.of(*range(1000)).pipe(take(1000)).subscribe(on_next=lambda x: None)',
        setup='import reactivex as rxx; from reactivex.operators import take',
        number=50
    )
    
    print(f"\ntake(全部)测试 (1000个元素，取全部):")
    print(f"  vools: {vools_full / 50 * 1000000:.2f}µs")
    print(f"  rxx:   {rxx_full / 50 * 1000000:.2f}µs")
    print(f"  性能比: {rxx_full / vools_full:.2f}x")


def test_take_correctness():
    """验证take操作符功能正确性"""
    print("\n" + "=" * 80)
    print("take操作符功能验证")
    print("=" * 80)
    
    # 测试正常情况
    result = []
    rx.of(*range(100)).pipe(rx.take(10)).subscribe(on_next=lambda x: result.append(x))
    
    if len(result) == 10 and result == list(range(10)):
        print("✅ 正常take测试通过")
    else:
        print(f"❌ 正常take测试失败: 预期10个元素[0-9], 实际{len(result)}个元素{result}")
    
    # 测试take(0)
    result = []
    rx.of(*range(100)).pipe(rx.take(0)).subscribe(on_next=lambda x: result.append(x))
    
    if len(result) == 0:
        print("✅ take(0)测试通过")
    else:
        print(f"❌ take(0)测试失败: 预期0个元素, 实际{len(result)}个元素")
    
    # 测试take超过总量
    result = []
    rx.of(*range(10)).pipe(rx.take(100)).subscribe(on_next=lambda x: result.append(x))
    
    if len(result) == 10 and result == list(range(10)):
        print("✅ take超过总量测试通过")
    else:
        print(f"❌ take超过总量测试失败: 预期10个元素[0-9], 实际{len(result)}个元素{result}")


if __name__ == "__main__":
    test_take_correctness()
    benchmark_take()
    benchmark_edge_cases()
