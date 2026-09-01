#include <cstdlib>
#include <string>

int add(int a, int b);

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::string stage = argv[1];
  if (stage == "public") return add(2, 3) == 5 ? 0 : 1;
  if (stage == "hidden") return add(-2, 3) == 1 ? 0 : 1;
  if (stage == "regression") return add(0, 0) == 0 ? 0 : 1;
  return 2;
}
