# Cross-study identity: draft-study and shot-quality-study claim the same
# hand-rolled IRLS in R; hold them to it on shared random data.

test_that("IRLS agrees between draft-study and shot-quality-study", {
  dr <- new.env(); sq <- new.env()
  source(file.path(REPO, "..", "draft-study", "R", "functions.R"), local = dr)
  source(file.path(REPO, "..", "shot-quality-study", "R", "functions.R"),
         local = sq)
  set.seed(3)
  X <- cbind(1, matrix(rnorm(600), ncol = 2))
  y <- as.numeric(runif(300) < 0.4)
  expect_equal(dr$logistic_irls(X, y), sq$logistic_irls(X, y),
               tolerance = 1e-12)
})
