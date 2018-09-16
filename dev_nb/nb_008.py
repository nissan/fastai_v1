
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################
        # file to edit: /data1/jhoward/git/fastai_v1/dev_nb/008_movie_lens.ipynb

from nb_007a import *
from pandas import Series,DataFrame

def series2cat(df, *col_names):
    for c in listify(col_names): df[c] = df[c].astype('category').cat.as_ordered()

@dataclass
class ColabFilteringDataset():
    user:Series
    item:Series
    ratings:DataFrame
    def __post_init__(self):
        self.user_ids = np.array(self.user.cat.codes, dtype=np.int64)
        self.item_ids = np.array(self.item.cat.codes, dtype=np.int64)

    def __len__(self): return len(self.ratings)

    def __getitem__(self, idx):
        return (self.user_ids[idx],self.item_ids[idx]), self.ratings[idx]

    @property
    def n_user(self): return len(self.user.cat.categories)

    @property
    def n_item(self): return len(self.item.cat.categories)

    @classmethod
    def from_df(cls, rating_df, pct_val=0.2, user_name=None, item_name=None, rating_name=None):
        if user_name is None:   user_name = rating_df.columns[0]
        if item_name is None:   item_name = rating_df.columns[1]
        if rating_name is None: rating_name = rating_df.columns[2]
        user = rating_df[user_name]
        item = rating_df[item_name]
        ratings = np.array(rating_df[rating_name], dtype=np.float32)
        idx = np.random.permutation(len(ratings))
        cut = int(pct_val * len(ratings))
        return (cls(user[idx[cut:]], item[idx[cut:]], ratings[idx[cut:]]),
                cls(user[idx[:cut]], item[idx[:cut]], ratings[idx[:cut]]))

    @classmethod
    def from_csv(cls, csv_name, **kwargs):
        df = pd.read_csv(csv_name)
        return cls.from_df(df, **kwargs)

def trunc_normal_(x, mean=0., std=1.):
    # From https://discuss.pytorch.org/t/implementing-truncated-normal-initializer/4778/12
    return x.normal_().fmod_(2).mul_(std).add_(mean)

def get_embedding(ni,nf):
    emb = nn.Embedding(ni, nf)
    # See https://arxiv.org/abs/1711.09160
    with torch.no_grad(): trunc_normal_(emb.weight, std=0.01)
    return emb

class EmbeddingDotBias(nn.Module):
    def __init__(self, n_factors, n_users, n_items, min_score=None, max_score=None):
        super().__init__()
        self.min_score,self.max_score = min_score,max_score
        (self.u_weight, self.i_weight, self.u_bias, self.i_bias) = [get_embedding(*o) for o in [
            (n_users, n_factors), (n_items, n_factors), (n_users,1), (n_items,1)
        ]]

    def forward(self, users, items):
        dot = self.u_weight(users)* self.i_weight(items)
        res = dot.sum(1) + self.u_bias(users).squeeze() + self.i_bias(items).squeeze()
        if self.min_score is None: return res
        return torch.sigmoid(res) * (self.max_score-self.min_score) + self.min_score