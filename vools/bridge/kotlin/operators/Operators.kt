package com.example.operators

/**
 * Kotlin 隐式双元操作符库 - 函数组合与管道操作
 *
 * 提供两组操作符：
 * 1. 函|函操作符（#gt/#gtgt/~gt/~gtgt/~~gt/~~gtgt 及其反向和星号变体）- 用于函数组合
 * 2. 值|函管道操作符（pipe/pipeMap/pipeFilter/pipeFlat/pipeReduce/pipeFold 及其反向）- 用于值到函数的管道应用
 *
 * 使用方式：
 * ```kotlin
 * import com.example.operators.Operators.*
 *
 * // 函数组合
 * val composed = #gt({ "Hello" }, { s: String -> "$s, World!" })
 * println(composed())  // 输出: Hello, World!
 *
 * // 管道操作
 * val result = pipe("hello") { it.uppercase() }
 * println(result)  // 输出: HELLO
 * ```
 */
object Operators {

    // ============ 零参数函数到单参数函数 ============

    fun <A, B> `#gt`(f: () -> A, g: (A) -> B): () -> B = { g(f()) }

    fun <A, B> `lt#`(g: (A) -> B, f: () -> A): () -> B = { g(f()) }

    fun <A, B, X> `#gtgt`(f: () -> A, g: (A, X) -> B): (X) -> B = { x -> g(f(), x) }

    fun <A, B, X> `ltlt#`(g: (A, X) -> B, f: () -> A): (X) -> B = { x -> g(f(), x) }

    fun <A, B, X> `star#gt`(f: () -> Iterable<A>, g: (A, X) -> B): (X) -> B = { x ->
        val result = f().firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, X> `star#gt`(f: () -> Pair<A, B>, g: (A, B, X) -> C): (X) -> C = { x ->
        val (a, b) = f()
        g(a, b, x)
    }

    fun <A, B, X> `lt#star`(g: (A, X) -> B, f: () -> Iterable<A>): (X) -> B = { x ->
        val result = f().firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, X> `lt#star`(g: (A, B, X) -> C, f: () -> Pair<A, B>): (X) -> C = { x ->
        val (a, b) = f()
        g(a, b, x)
    }

    // ============ 单参数函数组合 ============

    fun <A, B, C> `~gt`(f: (A) -> B, g: (B) -> C): (A) -> C = { a -> g(f(a)) }

    fun <A, B, C> `lt~`(g: (B) -> C, f: (A) -> B): (A) -> C = { a -> g(f(a)) }

    fun <A, B, C, X> `~gtgt`(f: (A) -> B, g: (B, X) -> C): (A, X) -> C = { a, x -> g(f(a), x) }

    fun <A, B, C, X> `ltlt~`(g: (B, X) -> C, f: (A) -> B): (A, X) -> C = { a, x -> g(f(a), x) }

    fun <A, B, C, X> `star~gt`(f: (A) -> Iterable<B>, g: (B, X) -> C): (A, X) -> C = { a, x ->
        val result = f(a).firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, D, X> `star~gt`(f: (A) -> Pair<B, C>, g: (B, C, X) -> D): (A, X) -> D = { a, x ->
        val (b, c) = f(a)
        g(b, c, x)
    }

    fun <A, B, C, X> `lt~star`(g: (B, X) -> C, f: (A) -> Iterable<B>): (A, X) -> C = { a, x ->
        val result = f(a).firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, D, X> `lt~star`(g: (B, C, X) -> D, f: (A) -> Pair<B, C>): (A, X) -> D = { a, x ->
        val (b, c) = f(a)
        g(b, c, x)
    }

    // ============ 双参数函数组合 ============

    fun <A, B, C, D> `~~gt`(f: (A, B) -> C, g: (C) -> D): (A, B) -> D = { a, b -> g(f(a, b)) }

    fun <A, B, C, D> `lt~~`(g: (C) -> D, f: (A, B) -> C): (A, B) -> D = { a, b -> g(f(a, b)) }

    fun <A, B, C, D, X> `~~gtgt`(f: (A, B) -> C, g: (C, X) -> D): (A, B, X) -> D = { a, b, x -> g(f(a, b), x) }

    fun <A, B, C, D, X> `ltlt~~`(g: (C, X) -> D, f: (A, B) -> C): (A, B, X) -> D = { a, b, x -> g(f(a, b), x) }

    fun <A, B, C, D, X> `star~~gt`(f: (A, B) -> Iterable<C>, g: (C, X) -> D): (A, B, X) -> D = { a, b, x ->
        val result = f(a, b).firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, D, E, X> `star~~gt`(f: (A, B) -> Pair<C, D>, g: (C, D, X) -> E): (A, B, X) -> E = { a, b, x ->
        val (c, d) = f(a, b)
        g(c, d, x)
    }

    fun <A, B, C, D, X> `lt~~star`(g: (C, X) -> D, f: (A, B) -> Iterable<C>): (A, B, X) -> D = { a, b, x ->
        val result = f(a, b).firstOrNull() ?: throw NoSuchElementException("Cannot unpack empty sequence")
        g(result, x)
    }

    fun <A, B, C, D, E, X> `lt~~star`(g: (C, D, X) -> E, f: (A, B) -> Pair<C, D>): (A, B, X) -> E = { a, b, x ->
        val (c, d) = f(a, b)
        g(c, d, x)
    }

    // ============ 值到函数管道操作符 ============

    fun <A, B> pipe(value: A, f: (A) -> B): B = f(value)

    fun <A, B> pipeLeft(f: (A) -> B, value: A): B = f(value)

    fun <A, B> pipeMap(values: Iterable<A>, f: (A) -> B): List<B> = values.map(f)

    fun <A, B> pipeMapLeft(f: (A) -> B, values: Iterable<A>): List<B> = values.map(f)

    fun <A> pipeFilter(values: Iterable<A>, predicate: (A) -> Boolean): List<A> = values.filter(predicate)

    fun <A> pipeFilterLeft(predicate: (A) -> Boolean, values: Iterable<A>): List<A> = values.filter(predicate)

    fun <A, B> pipeFlat(values: Iterable<Iterable<A>>, f: (A) -> B): List<B> = values.flatMap { it.map(f) }

    fun <A, B> pipeFlatLeft(f: (A) -> B, values: Iterable<Iterable<A>>): List<B> = values.flatMap { it.map(f) }

    fun <A> pipeReduce(values: Iterable<A>, f: (A, A) -> A): A = values.reduce(f)

    fun <A> pipeReduceLeft(f: (A, A) -> A, values: Iterable<A>): A = values.reduce(f)

    fun <A, Z> pipeFold(values: Iterable<A>, folder: (Z) -> (Z, A) -> Z): (Z) -> Z = { init ->
        values.fold(init) { acc, a -> folder(init)(acc, a) }
    }

    fun <A, Z> pipeFoldLeft(folder: (Z) -> (Z, A) -> Z, values: Iterable<A>): (Z) -> Z = { init ->
        values.fold(init) { acc, a -> folder(init)(acc, a) }
    }
}
