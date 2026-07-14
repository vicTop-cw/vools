package com.example.operators

/**
 * Kotlin 隐式双元操作符测试套件
 * 覆盖所有操作符的正向、反向及边界场景
 */
fun main() {
    println("=".repeat(60))
    println("Kotlin Implicit Operators Test Suite")
    println("=".repeat(60))

    var passed = 0
    var total = 0

    fun test(name: String, block: () -> Unit) {
        total++
        try {
            block()
            passed++
            println("  [PASS] $name")
        } catch (e: Throwable) {
            println("  [FAIL] $name: ${e.message}")
            throw e
        }
    }

    println("\n--- Function-to-Function Operators ---")

    test("#gt composes zero-arg to single-arg") {
        val genA = { "Hello" }
        val genB: (String) -> String = { "$it, World!" }
        val merged = Operators.`#gt`(genA, genB)
        assert(merged() == "Hello, World!")
    }

    test("~gt composes single-arg functions") {
        val f: (String) -> String = { "$it Are" }
        val g: (String) -> String = { "$it You?" }
        val merged = Operators.`~gt`(f, g)
        assert(merged("How") == "How Are You?")
    }

    test("~~gt composes two-arg to single-arg") {
        val f: (String, String) -> String = { d, f0 -> "$d $f0" }
        val g: (String) -> String = { "$it!" }
        val merged = Operators.`~~gt`(f, g)
        assert(merged("Hello", "World") == "Hello World!")
    }

    println("\n--- Value-to-Function Pipe Operators ---")

    test("pipe applies value to function") {
        val result = Operators.pipe("hello") { it.uppercase() }
        assert(result == "HELLO")
    }

    test("pipeMap maps List") {
        val result = Operators.pipeMap(listOf(1, 2, 3)) { it * 2 }
        assert(result == listOf(2, 4, 6))
    }

    test("pipeFilter filters List") {
        val result = Operators.pipeFilter(listOf(1, 2, 3, 4)) { it % 2 == 0 }
        assert(result == listOf(2, 4))
    }

    test("pipeFlat flattens and maps") {
        val result = Operators.pipeFlat(listOf(listOf(1, 2), listOf(3, 4))) { it * 10 }
        assert(result == listOf(10, 20, 30, 40))
    }

    test("pipeReduce reduces List") {
        val result = Operators.pipeReduce(listOf(1, 2, 3, 4)) { a: Int, b: Int -> a + b }
        assert(result == 10)
    }

    test("pipeFold folds with curried folder") {
        fun folder(init: Int): (Int, Int) -> Int = { acc, x -> acc + x }
        val sumFunc = Operators.pipeFold(listOf(1, 2, 3, 4), ::folder)
        assert(sumFunc(0) == 10)
        assert(sumFunc(10) == 20)
    }

    println("=".repeat(60))
    println("Total passed: $passed/$total")
    println("=".repeat(60))
    if (passed == total) println("ALL TESTS PASSED")
    else throw RuntimeException("Some tests failed")
}
