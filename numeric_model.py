import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from word2vec_model import PlayerEmbedding
import random
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

class Model(nn.Module):

    def __init__(self, embedding_size, num_numerical_cols, output_size, layers, p=0.4):
        super().__init__()
        self.all_embeddings = nn.ModuleList([nn.Embedding(ni, nf) for ni, nf in embedding_size])
        self.embedding_dropout = nn.Dropout(p)
        self.batch_norm_num = nn.BatchNorm1d(num_numerical_cols)

        all_layers = []
        num_categorical_cols = sum((nf for ni, nf in embedding_size))
        input_size = num_categorical_cols + num_numerical_cols

        for i in layers:
            all_layers.append(nn.Linear(input_size, i))
            all_layers.append(nn.ReLU(inplace=True))
            all_layers.append(nn.BatchNorm1d(i))
            all_layers.append(nn.Dropout(p))
            input_size = i

        all_layers.append(nn.Linear(layers[-1], output_size))

        self.layers = nn.Sequential(*all_layers)

    def forward(self, x_categorical, x_numerical):
        embeddings = []
        for i, e in enumerate(self.all_embeddings):
            embeddings.append(e(x_categorical[:, i]))
        x = torch.cat(embeddings, 1)
        x = self.embedding_dropout(x)

        x_numerical = self.batch_norm_num(x_numerical)
        x = torch.cat([x, x_numerical], 1)
        x = self.layers(x)
        return x


class ModelTrainer:
    DATA_MATRIX = None
    CATEGORIES = ["League", "TeamHome", "TeamAway", "ManagerHome", "ManagerAway", "FormationHome", "FormationAway", "Stadium",
                  "Referee", "FutureTeamHome", "FutureTeamAway", "FutureStatusTeamHome", "FutureStatusTeamAway"]
    INVALID = ["Result", "Total2.5", "Total1.5", "TeamHomeStr", "TeamAwayStr", "Date", "StartTeamHome", "StartTeamAway",
               "SubsTeamHome", "SubsTeamAway"]

    numeric_matrix = None
    emb_matrix = None
    categorical_embedding_sizes = None

    cat_train = None
    cat_test = None
    num_train = None
    num_test = None

    result_train = None
    result_test = None

    def __init__(self, league_name: str):
        self.league_name = league_name
        self.DATA_MATRIX = pd.read_csv(league_name + "_learn_data.csv", delimiter=';')
        self.RESULT = self.DATA_MATRIX["Result"]

        self.define_learn_data()
        self.split_data()

        self.MODEL = Model(self.categorical_embedding_sizes, self.numeric_matrix.shape[1], 3, [200, 100, 50])

        self.loss_function = nn.CrossEntropyLoss()
        self.optimizer = torch.optim.Adam(self.MODEL.parameters(), lr=0.001)

    def define_learn_data(self):
        # emb data
        self.emb_matrix = np.stack([self.DATA_MATRIX[col].values for col in self.CATEGORIES], 1)
        self.emb_matrix = torch.tensor(self.emb_matrix, dtype=torch.int64)
        # num matrix
        num_list = list()
        for col_key in self.DATA_MATRIX.keys():
            if col_key not in self.INVALID and col_key not in self.CATEGORIES:
                num_list.append(col_key)

        self.numeric_matrix = np.stack([self.DATA_MATRIX[col].values for col in num_list], 1)
        # self.numeric_matrix = torch.tensor(self.numeric_matrix, dtype=torch.float)

        for category in self.CATEGORIES:
            self.DATA_MATRIX[category] = self.DATA_MATRIX[category].astype('category')

        categorical_column_sizes = [len(self.DATA_MATRIX[column].cat.categories) for column in self.CATEGORIES]
        self.categorical_embedding_sizes = [(col_size, min(50, (col_size + 1) // 2)) for col_size in
                                            categorical_column_sizes]

    def split_data(self, ratio=0.2):
        total_matches = self.DATA_MATRIX.shape[0]
        train_matches = int((1-ratio) * total_matches)

        index_list = list(range(total_matches))
        train_index_list = index_list[:train_matches]
        random.shuffle(index_list)

        new_cat_matrix_train = list()
        new_cat_matrix_test = list()
        new_num_matrix_train = list()
        new_num_matrix_test = list()
        new_result_train = list()
        new_result_test = list()

        for match_i in range(total_matches):
            if match_i in train_index_list:
                new_cat_matrix_train.append(self.emb_matrix[match_i, :])
                new_num_matrix_train.append(self.numeric_matrix[match_i, :])
                new_result_train.append(self.RESULT[match_i])
            else:
                new_cat_matrix_test.append(self.emb_matrix[match_i, :])
                new_num_matrix_test.append(self.numeric_matrix[match_i, :])
                new_result_test.append(self.RESULT[match_i])

        self.cat_train =torch.tensor(np.stack(new_cat_matrix_train, 0), dtype=torch.int64)
        self.cat_test = torch.tensor(np.stack(new_cat_matrix_test, 0), dtype=torch.int64)
        self.num_train = torch.tensor(np.stack(new_num_matrix_train, 0), dtype=torch.float)
        self.num_test = torch.tensor(np.stack(new_num_matrix_test, 0), dtype=torch.float)
        self.result_train = torch.tensor(np.stack(new_result_train), dtype=torch.int64).flatten()
        self.result_test = torch.tensor(np.stack(new_result_test), dtype=torch.int64).flatten()

    def train_model(self, epochs=300):

        aggregated_losses = []
        single_loss = dict()

        for i in range(epochs):
            i += 1
            y_pred = self.MODEL.forward(self.cat_train, self.num_train)
            single_loss = self.loss_function(y_pred, self.result_train)
            aggregated_losses.append(single_loss)

            if i % 25 == 1:
                print(f'epoch: {i:3} loss: {single_loss.item():10.8f}')

            self.optimizer.zero_grad()
            single_loss.backward()
            self.optimizer.step()

        print(f'epoch: {epochs:3} loss: {single_loss.item():10.10f}')
        plt.plot(range(epochs), aggregated_losses)
        plt.ylabel('Loss')
        plt.xlabel('epoch')
        plt.show()

    def test_model(self):
        with torch.no_grad():
            y_val = self.MODEL(self.cat_test, self.num_test)
            loss = self.loss_function(y_val, self.result_test)
        print(f'Loss: {loss:.8f}')
        print(confusion_matrix(self.result_test, y_val))
        print(classification_report(self.result_test, y_val))
        print(accuracy_score(self.result_test, y_val))


my_class = ModelTrainer("LaLiga (Spain)")
my_class.train_model()
my_class.test_model()