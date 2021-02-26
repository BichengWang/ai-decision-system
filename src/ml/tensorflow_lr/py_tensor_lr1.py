import tensorflow as tf
import numpy as np

train_step = 1000

x_data = np.random.rand(100).astype(np.float32)
y_data = x_data * 0.1 + 0.3

weights = tf.Variable(tf.random_uniform_initializer([1], -1.0, 1.0))
biases = tf.Variable(tf.zeros([1]))

y = weights * x_data + biases

loss = tf.reduce_mean(tf.square(y - y_data))

optimizer = tf.keras.optimizers.SGD(0.5)

train = optimizer.minimize(loss)

init = tf.compat.v1.global_variables_initializer()

sess = tf.Session()

sess.run(init)


for step in range(train_step):
    sess.run(train)
    if step % 20 == 0:
        print(step, sess.run(weights), sess.run(biases))

