package com.example.operators

import Operators._

/**
 * Scala 隐式双元操作符测试套件。
 * 覆盖所有 30 个操作符的正向、反向及边界场景。
 *
 * 使用方式：
 *   1. 编译：scalac -d target/classes Operators.scala OperatorsTest.scala
 *   2. 运行：scala -cp target/classes com.example.operators.OperatorsTest
 */
object OperatorsTest {

  private var testCount = 0
  private var passCount = 0

  def main(args: Array[String]): Unit = {
    println("=" * 60)
    println("Scala Implicit Operators Test Suite")
    println("=" * 60)

    runFunctionOperatorsTests()
    runPipeOperatorsTests()

    println("=" * 60)
    println(s"Total passed: $passCount/$testCount")
    println("=" * 60)
    if (passCount == testCount) println("ALL TESTS PASSED")
    else sys.exit(1)
  }

  def runFunctionOperatorsTests(): Unit = {
    println("\n--- Function-to-Function Operators ---")

    // #> / <#
    test("#> composes zero-arg to single-arg") {
      def genA(): String = "Hello"
      def genB(s: String): String = s"$s, World!"
      val merged = genA _ #> genB _
      assert(merged() == "Hello, World!")
    }

    test("<# reverses zero-arg to single-arg") {
      def genA(): String = "Hello"
      def genB(s: String): String = s"$s, World!"
      val merged = genB _ <# genA _
      assert(merged() == "Hello, World!")
    }

    // #>> / <<#
    test("#>> composes zero-arg to two-arg") {
      def genA(): String = "Hello"
      def genB(s: String, name: String): String = s"$s, $name!"
      val merged = genA _ #>> genB _
      assert(merged("World") == "Hello, World!")
    }

    test("<<# reverses zero-arg to two-arg") {
      def genA(): String = "Hello"
      def genB(s: String, name: String): String = s"$s, $name!"
      val merged = genB _ <<# genA _
      assert(merged("World") == "Hello, World!")
    }

    // *#> / <#*
    test("*#> unpacks Seq head") {
      def genA(): List[String] = List("Hello")
      def genB(s: String, name: String): String = s"$s, $name!"
      val merged = genA _ *#> genB _
      assert(merged("World") == "Hello, World!")
    }

    test("*#> unpacks Tuple2") {
      def genA(): (String, String) = ("Hello", "World")
      def genB(a: String, b: String, c: String): String = s"$a, $b, $c!"
      val merged = genA _ *#> genB _
      assert(merged("Scala") == "Hello, World, Scala!")
    }

    test("<#* reverses with Seq") {
      def genA(): List[String] = List("Hello")
      def genB(s: String, name: String): String = s"$s, $name!"
      val merged = genB _ <#* genA _
      assert(merged("World") == "Hello, World!")
    }

    test("<#* reverses with Tuple2") {
      def genA(): (String, String) = ("Hello", "World")
      def genB(a: String, b: String, c: String): String = s"$a, $b, $c!"
      val merged = genB _ <#* genA _
      assert(merged("Scala") == "Hello, World, Scala!")
    }

    test("*#> throws on empty Seq") {
      def genEmpty(): List[String] = Nil
      def genB(s: String, name: String): String = s"$s, $name!"
      val merged = genEmpty _ *#> genB _
      var caught = false
      try { merged("World") } catch { case _: NoSuchElementException => caught = true }
      assert(caught)
    }

    // ~> / <~
    test("~> composes single-arg functions") {
      def f(h: String): String = s"$h Are"
      def g(s: String): String = s"$s You?"
      val merged = f _ ~> g _
      assert(merged("How") == "How Are You?")
    }

    test("<~ reverses single-arg composition") {
      def f(h: String): String = s"$h Are"
      def g(s: String): String = s"$s You?"
      val merged = g _ <~ f _
      assert(merged("How") == "How Are You?")
    }

    // ~>> / <<~
    test("~>> composes single-arg to two-arg") {
      def f(h: String): String = s"$h Are"
      def g(s: String, name: String): String = s"$s You? $name!"
      val merged = f _ ~>> g _
      assert(merged("How", "Victor") == "How Are You? Victor!")
    }

    test("<<~ reverses single-arg to two-arg") {
      def f(h: String): String = s"$h Are"
      def g(s: String, name: String): String = s"$s You? $name!"
      val merged = g _ <<~ f _
      assert(merged("How", "Victor") == "How Are You? Victor!")
    }

    // *~> / <~*
    test("*~> unpacks Seq from single-arg") {
      def f(name: String): List[String] = List("Hi")
      def g(s: String, name: String): String = s"$s, $name!"
      val merged = f _ *~> g _
      assert(merged("Victor", "World") == "Hi, World!")
    }

    test("*~> unpacks Tuple2 from single-arg") {
      def f(name: String): (String, String) = ("Hi", name)
      def g(s: String, name: String, other: String): String = s"$s, $name, $other"
      val merged = f _ *~> g _
      assert(merged("Victor", "what can I do for you?") == "Hi, Victor, what can I do for you?")
    }

    test("<~* reverses with Seq") {
      def f(name: String): List[String] = List("Hi")
      def g(s: String, name: String): String = s"$s, $name!"
      val merged = g _ <~* f _
      assert(merged("Victor", "World") == "Hi, World!")
    }

    test("<~* reverses with Tuple2") {
      def f(name: String): (String, String) = ("Hi", name)
      def g(s: String, name: String, other: String): String = s"$s, $name, $other"
      val merged = g _ <~* f _
      assert(merged("Victor", "what can I do for you?") == "Hi, Victor, what can I do for you?")
    }

    // ~~> / <~~
    test("~~> composes two-arg to single-arg") {
      def f(d: String, f0: String): String = s"$d $f0"
      def g(s: String): String = s"$s!"
      val merged = f _ ~~> g _
      assert(merged("Hello", "World") == "Hello World!")
    }

    test("<~~ reverses two-arg to single-arg") {
      def f(d: String, f0: String): String = s"$d $f0"
      def g(s: String): String = s"$s!"
      val merged = g _ <~~ f _
      assert(merged("Hello", "World") == "Hello World!")
    }

    // *~~> / <~~*
    test("*~~> unpacks Seq from two-arg") {
      def f(d: String, f0: String): List[String] = List(d)
      def g(a: String, b: String): String = s"$a, $b"
      val merged = f _ *~~> g _
      assert(merged("Hello", "World", "!") == "Hello, !")
    }

    test("*~~> unpacks Tuple2 from two-arg") {
      def f(d: String, f0: String): (String, String) = (d, f0)
      def g(a: String, b: String, c: String): String = s"$a, $b, $c"
      val merged = f _ *~~> g _
      assert(merged("Hello", "World", "!") == "Hello, World, !")
    }

    test("<~~* reverses with Seq") {
      def f(d: String, f0: String): List[String] = List(d)
      def g(a: String, b: String): String = s"$a, $b"
      val merged = g _ <~~* f _
      assert(merged("Hello", "World", "!") == "Hello, !")
    }

    test("<~~* reverses with Tuple2") {
      def f(d: String, f0: String): (String, String) = (d, f0)
      def g(a: String, b: String, c: String): String = s"$a, $b, $c"
      val merged = g _ <~~* f _
      assert(merged("Hello", "World", "!") == "Hello, World, !")
    }

    test("*~~> throws on empty Seq") {
      def f(d: String, f0: String): List[String] = Nil
      def g(a: String): String = a
      val merged = f _ *~~> g _
      var caught = false
      try { merged("Hello", "World") } catch { case _: NoSuchElementException => caught = true }
      assert(caught)
    }

    // ~~>> / <<~~
    test("~~>> composes two-arg to two-arg") {
      def f(d: String, f0: String): String = s"$d $f0"
      def g(s: String, name: String): String = s"$s, $name!"
      val merged = f _ ~~>> g _
      assert(merged("Hello", "World", "Victor") == "Hello World, Victor!")
    }

    test("<<~~ reverses two-arg to two-arg") {
      def f(d: String, f0: String): String = s"$d $f0"
      def g(s: String, name: String): String = s"$s, $name!"
      val merged = g _ <<~~ f _
      assert(merged("Hello", "World", "Victor") == "Hello World, Victor!")
    }

    // Composed functions work with standard library
    test("composed ~> works in List.map") {
      def inc(x: Int): Int = x + 1
      def toStr(x: Int): String = x.toString
      val mapper: Int => String = inc _ ~> toStr _
      assert(List(1, 2, 3).map(mapper) == List("2", "3", "4"))
    }

    test("composed #>> works in List.map") {
      def constant(): Int = 10
      def multiply(base: Int, x: Int): Int = base * x
      val scaler: Int => Int = constant _ #>> multiply _
      assert(List(1, 2, 3).map(scaler) == List(10, 20, 30))
    }
  }

  def runPipeOperatorsTests(): Unit = {
    println("\n--- Value-to-Function Pipe Operators ---")

    // |> / <|
    test("|> applies value to function") {
      val result = "hello" |> (_.toUpperCase)
      assert(result == "HELLO")
    }

    test("<| reverses value application") {
      val result = ((s: String) => s.toUpperCase) <| "hello"
      assert(result == "HELLO")
    }

    // |>> / <<|
    test("|>> maps List preserving type") {
      val result = List(1, 2, 3) |>> (_ * 2)
      assert(result == List(2, 4, 6))
      assert(result.isInstanceOf[List[_]])
    }

    test("<<| reverses map") {
      val result = ((x: Int) => x * 2) <<| List(1, 2, 3)
      assert(result == List(2, 4, 6))
    }

    test("|>> returns empty for empty input") {
      val result = List.empty[Int] |>> (_ * 2)
      assert(result == Nil)
    }

    // |?> / <|?
    test("|?> filters List") {
      val result = List(1, 2, 3, 4) |?> (_ % 2 == 0)
      assert(result == List(2, 4))
    }

    test("<|? reverses filter") {
      val result = ((x: Int) => x % 2 == 0) <|? List(1, 2, 3, 4)
      assert(result == List(2, 4))
    }

    test("|?> returns empty when no match") {
      val result = List(1, 3, 5) |?> (_ % 2 == 0)
      assert(result == Nil)
    }

    // |*> / <*|
    test("|*> flattens and maps") {
      val result = List(List(1, 2), List(3, 4)) |*> (_ * 10)
      assert(result == List(10, 20, 30, 40))
    }

    test("<*| reverses flatMap") {
      val result = ((x: Int) => x * 10) <*| List(List(1, 2), List(3, 4))
      assert(result == List(10, 20, 30, 40))
    }

    test("|*> handles empty outer") {
      val result = List.empty[List[Int]] |*> (_ * 10)
      assert(result == Nil)
    }

    // |&> / <&|
    test("|&> reduces List") {
      val result = List(1, 2, 3, 4) |&> (_ + _)
      assert(result == 10)
    }

    test("<&| reverses reduce") {
      val result = ((a: Int, b: Int) => a + b) <&| List(1, 2, 3, 4)
      assert(result == 10)
    }

    test("|&> throws on empty") {
      var caught = false
      try { List.empty[Int] |&> (_ + _) } catch { case _: UnsupportedOperationException => caught = true }
      assert(caught)
    }

    // |@> / <@|
    test("|@> folds with curried folder") {
      def folder(init: Int)(acc: Int, x: Int): Int = acc + x
      val sumFunc = List(1, 2, 3, 4) |@> folder _
      assert(sumFunc(0) == 10)
      assert(sumFunc(10) == 20)
    }

    test("<@| reverses fold") {
      def folder(init: Int)(acc: Int, x: Int): Int = acc + x
      val sumFunc = folder _ <@| List(1, 2, 3, 4)
      assert(sumFunc(0) == 10)
    }

    test("|@> returns initial for empty") {
      def folder(init: Int)(acc: Int, x: Int): Int = acc + x
      val sumFunc = List.empty[Int] |@> folder _
      assert(sumFunc(100) == 100)
    }
  }

  private def test(name: String)(body: => Unit): Unit = {
    testCount += 1
    try {
      body
      passCount += 1
      println(s"  [PASS] $name")
    } catch {
      case e: Throwable =>
        println(s"  [FAIL] $name: ${e.getMessage}")
        throw e
    }
  }
}
